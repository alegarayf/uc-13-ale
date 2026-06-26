"""
legal_contracts_agent.py — Phase 3: Legal & Contracts Workstream Agent.

Extracts contract terms and litigation exposure from documents tagged LEGAL. Receives
contract review triggers from customer_quality_agent.py (customers >20% of revenue)
and prioritizes those contracts as "triggered reviews."

Does not provide legal advice. Produces a structured contract register and CoC
consent list for the deal team and outside counsel.

Phase 3 outputs:
  - Table {catalog}.analysis.legal (M0 write target)
  - Compat view {catalog}.analysis.legal_contracts (legacy consumers)

Dependencies:
  - uc13.ingestion.embeddings
  - uc13.classification.doc_relevance
  - uc13.classification.company_profile
  - uc13.analysis.customer_quality      (reads contract_trigger_list)
  - agents.shared.retrieval.semantic_search
  - agents.shared.agent_base.WorkstreamAgent
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Secrets / params helpers — copied verbatim from financial_trends_agent.py
# ---------------------------------------------------------------------------

def _get_dbutils():
    """Return the Databricks dbutils object from any execution context.

    Works whether the code runs directly in a notebook cell or is called from
    an imported module (where dbutils is not a direct global but is reachable
    via the IPython user namespace injected by Databricks).
    """
    try:
        return dbutils  # noqa: F821
    except NameError:
        pass
    try:
        import IPython
        user_ns = IPython.get_ipython().user_ns
        if "dbutils" in user_ns:
            return user_ns["dbutils"]
    except Exception:
        pass
    return None


def _load_dotenv_if_local():
    if _get_dbutils() is None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

_load_dotenv_if_local()


def get_secret(key: str) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            return _dbutils.secrets.get("uc13", key)
        except Exception:
            pass
    value = os.environ.get(key)
    if value is None:
        raise RuntimeError(
            f"Secret '{key}' not found. "
            "On Databricks: add it to the 'uc13' secrets scope. "
            "Locally: add it to your .env file or export it as an env var."
        )
    return value


def get_param(key: str, default: str = None) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            value = _dbutils.widgets.get(key)
            if value:
                return value
        except Exception:
            pass
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(
            f"Parameter '{key}' not found. "
            "On Databricks: add it as a job task parameter. "
            "Locally: add it to your .env file or export it as an env var."
        )
    return value


# ---------------------------------------------------------------------------
# Repo root resolver — copied verbatim from financial_trends_agent.py
# ---------------------------------------------------------------------------

def get_current_path():
    try:
        notebook_path = (
            dbutils.notebook.entry_point  # noqa: F821
            .getDbutils()
            .notebook()
            .getContext()
            .notebookPath()
            .get()
        )
        return Path("/Workspace") / notebook_path.lstrip("/")
    except Exception:
        return Path(os.getcwd())


def find_repo_root(marker="agents"):
    current_path = get_current_path()
    if current_path.is_file():
        current_path = current_path.parent
    for path in [current_path, *current_path.parents]:
        if (path / marker).exists():
            return str(path)
    raise RuntimeError(f"Could not find a parent directory containing '{marker}'")


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _parse_int(value) -> Optional[int]:
    """Parse to int, stripping whitespace. Returns None on failure."""
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _is_true(value) -> bool:
    """True only for string token 'true' (case-insensitive) — §5.6.1."""
    return str(value or "").strip().lower() == "true"


def _is_not_found(value) -> bool:
    """True when LLM emitted the not_found tri-state token — §5.6.1."""
    return str(value or "").strip().lower() == "not_found"


def _eq_str(value, expected: str) -> bool:
    """Case-insensitive string equality for LLM string tokens — §5.6.1."""
    return str(value or "").strip().lower() == expected.lower()


def _normalize_name(value) -> str:
    """Strip, collapse whitespace, casefold for within-register dedupe keys — §5.6.2."""
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _raw_quote_len(record: dict) -> int:
    return len(str(record.get("raw_quote") or ""))


def _union_citation_field(existing, incoming) -> str:
    """Union source_doc / raw_quote values when dedupe merges rows — §5.6.2."""
    parts: list[str] = []
    for value in (existing, incoming):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    if parts:
        return " | ".join(parts)
    return str(existing or incoming or "")


def _merge_nested_dicts(base: dict, overlay: dict) -> dict:
    """Merge nested clause dicts; non-null fields from both sides are retained."""
    merged = dict(base)
    for key, val in overlay.items():
        if val is None:
            continue
        if key not in merged or merged[key] is None:
            merged[key] = val
        elif isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _merge_nested_dicts(merged[key], val)
    return merged


def _merge_register_records(existing: dict, incoming: dict) -> dict:
    """Within-register conflict resolution — prefer row with longer raw_quote — §5.6.2."""
    preferred = existing if _raw_quote_len(existing) >= _raw_quote_len(incoming) else incoming
    other = incoming if preferred is existing else existing
    merged = dict(preferred)
    for key, val in other.items():
        if val is None:
            continue
        if key not in merged or merged[key] is None:
            merged[key] = val
        elif key in ("source_doc", "raw_quote"):
            merged[key] = _union_citation_field(merged[key], val)
        elif isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _merge_nested_dicts(merged[key], val)
    return merged


def _register_dedupe_key(register_name: str, record: dict) -> tuple:
    """Compute within-register dedupe key per §5.6.2 / §5.8 shapes."""
    if register_name == "contract_register":
        return (
            _normalize_name(record.get("counterparty_name")),
            str(record.get("contract_type") or "").strip().lower(),
        )
    if register_name == "vendor_register":
        return (
            _normalize_name(record.get("vendor_name")),
            str(record.get("agreement_type") or "").strip().lower(),
        )
    if register_name == "employment_register":
        return (
            _normalize_name(record.get("person_or_role")),
            str(record.get("agreement_class") or "").strip().lower(),
        )
    if register_name == "platform_dependency_register":
        return (
            _normalize_name(record.get("platform_or_channel_name")),
            str(record.get("dependency_type") or "").strip().lower(),
        )
    if register_name == "litigation_register":
        primary = record.get("counterparty") or record.get("description")
        return (
            _normalize_name(primary),
            str(record.get("matter_type") or "").strip().lower(),
        )
    if register_name == "ip_register":
        primary = record.get("ownership_assignment_note") or record.get("open_source_exposure_note")
        return (
            _normalize_name(primary),
            str(record.get("ip_type") or "").strip().lower(),
        )
    if register_name == "privacy_security_register":
        return (
            _normalize_name(record.get("description")),
            str(record.get("obligation_type") or "").strip().lower(),
        )
    if register_name == "insurance_register":
        primary = record.get("coverage_note") or record.get("gap_or_unusual_term_note")
        return (
            _normalize_name(primary),
            str(record.get("policy_type") or "").strip().lower(),
        )
    raise ValueError(f"Unknown register for dedupe: {register_name}")


# ---------------------------------------------------------------------------
# Per-pass LLM prompts (spec §5.8.1–5.8.5 — normative field names per D2a)
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM_PROMPT = """\
You are a senior PE investment analyst extracting structured legal diligence facts
from due diligence documents. Rules:
1. Extract ONLY what is explicitly stated in the provided context.
2. Do NOT infer, compute, assume, or hallucinate any value.
3. If a value is absent from the context, return null for that field.
4. Every extracted record must include source_doc, source_location, and raw_quote (≤30 words).
5. Return ONLY valid JSON with no preamble and no markdown fences.
6. Tri-state clause fields use JSON STRING tokens "true", "false", or "not_found" —
   never JSON boolean literals (true/false without quotes).
7. This agent does NOT provide legal advice. Extract facts only; do not opine on outcome.\
"""

_USER_PROMPT_CONTRACTS_VENDORS_PLATFORM = """\
COMPANY PROFILE (metadata only — do NOT treat as contract evidence):
{company_profile_json}

{trigger_context}

RETRIEVED DOCUMENT CONTEXT (extract ALL contract/vendor/platform facts from here):
{focused_chunk_text}

EXTRACTION TASK — contracts, vendors, and platform/channel dependencies (§5.8.1).
Extract one record per distinct contract, vendor agreement, or platform dependency.
Return ONLY this JSON object:

{{
  "contract_register": [
    {{
      "contract_id": "<sequential integer starting at 1>",
      "counterparty_name": "<name as stated>",
      "contract_type": "<MSA | SOW | Lease | Employment | Partnership | License | Vendor | Other>",
      "contract_date": "<date as stated or null>",
      "change_of_control": {{
        "clause_present": "<\"true\" | \"false\" | \"not_found\">",
        "consent_required": "<\"true\" | \"false\" | null>",
        "consent_standard": "<description as stated or null>",
        "ownership_threshold_pct": "<% as stated or null>"
      }},
      "termination_for_convenience": {{
        "present": "<\"true\" | \"false\" | \"not_found\">",
        "notice_days": "<integer as stated or null>",
        "penalty": "<description as stated or null>"
      }},
      "restrictive_covenants": {{
        "present": "<\"true\" | \"false\" | \"not_found\">",
        "scope_note": "<description as stated or null>"
      }},
      "auto_renewal": {{
        "present": "<\"true\" | \"false\" | \"not_found\">",
        "notice_for_non_renewal_days": "<integer or null>"
      }},
      "pricing_terms": {{
        "structure": "<fixed | indexed | customer_reset | escalator | null>",
        "customer_repricing_rights": "<\"true\" | \"false\" | null>"
      }},
      "liability_indemnity": {{
        "capped": "<\"true\" | \"false\" | null>",
        "cap_amount_note": "<description or null>",
        "unusual_indemnity": "<\"true\" | \"false\" | null>"
      }},
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote from a key clause>"
    }}
  ],
  "vendor_register": [
    {{
      "vendor_name": "<name as stated>",
      "agreement_type": "<MSA | SOW | Vendor | Supplier | Other>",
      "pricing_reset_terms": "<description as stated or null>",
      "cancellation_rights": "<description as stated or null>",
      "termination_notice_days": "<integer as stated or null>",
      "platform_criticality_note": "<description as stated or null>",
      "liability_indemnity": {{
        "capped": "<\"true\" | \"false\" | null>",
        "cap_amount_note": "<description or null>",
        "unusual_indemnity": "<\"true\" | \"false\" | null>"
      }},
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote>"
    }}
  ],
  "platform_dependency_register": [
    {{
      "platform_or_channel_name": "<name as stated>",
      "dependency_type": "<platform | reseller | channel | marketplace | other>",
      "exclusivity_note": "<description as stated or null>",
      "termination_impact_note": "<description as stated or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote>"
    }}
  ],
  "citations": [
    {{
      "field": "<field_name>",
      "document": "<exact filename>",
      "location": "<page, section, or tab>",
      "quote": "<≤30 word quote>",
      "confidence": "<high | medium | low>"
    }}
  ],
  "pass_notes": "<missing contracts, ambiguous clauses, documents not reviewed — or null>"
}}\
"""

_USER_PROMPT_EMPLOYMENT = """\
COMPANY PROFILE (metadata only):
{company_profile_json}

{trigger_context}

RETRIEVED DOCUMENT CONTEXT:
{focused_chunk_text}

EXTRACTION TASK — employment, contractor, commission, and founder/key agreements (§5.8.2).
Return ONLY this JSON object:

{{
  "employment_register": [
    {{
      "person_or_role": "<name or role as stated>",
      "agreement_class": "<employee | contractor | commission | founder_key>",
      "non_compete": {{
        "present": "<\"true\" | \"false\" | \"not_found\">",
        "scope_note": "<description as stated or null>"
      }},
      "non_solicit": {{
        "present": "<\"true\" | \"false\" | \"not_found\">",
        "scope_note": "<description as stated or null>"
      }},
      "change_of_control": {{
        "clause_present": "<\"true\" | \"false\" | \"not_found\">",
        "consent_required": "<\"true\" | \"false\" | null>",
        "consent_standard": "<description as stated or null>",
        "ownership_threshold_pct": "<% as stated or null>"
      }},
      "commission_terms_note": "<description as stated or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote>"
    }}
  ],
  "citations": [ {{ "field", "document", "location", "quote", "confidence" }} ],
  "pass_notes": "<string or null>"
}}\
"""

_USER_PROMPT_LITIGATION = """\
COMPANY PROFILE (metadata only):
{company_profile_json}

{trigger_context}

RETRIEVED DOCUMENT CONTEXT:
{focused_chunk_text}

EXTRACTION TASK — litigation, disputes, regulatory matters, and threatened claims (§5.8.3).
Capture every disclosed matter; do not filter or minimize.
Return ONLY this JSON object:

{{
  "litigation_register": [
    {{
      "matter_type": "<lawsuit | arbitration | regulatory | demand_letter | settlement | threatened | other>",
      "description": "<as stated>",
      "counterparty": "<name as stated or null>",
      "status": "<open | closed | unknown>",
      "estimated_exposure": "<$ as stated or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote>"
    }}
  ],
  "citations": [ {{ "field", "document", "location", "quote", "confidence" }} ],
  "pass_notes": "<string or null>"
}}\
"""

_USER_PROMPT_IP_PRIVACY = """\
COMPANY PROFILE (metadata only):
{company_profile_json}

{trigger_context}

RETRIEVED DOCUMENT CONTEXT:
{focused_chunk_text}

EXTRACTION TASK — intellectual property and data privacy/security obligations (§5.8.4).
Return ONLY this JSON object:

{{
  "ip_register": [
    {{
      "ip_type": "<patent | trademark | copyright | trade_secret | assignment | OSS | other>",
      "ownership_assignment_note": "<description as stated or null>",
      "open_source_exposure_note": "<description as stated or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote>"
    }}
  ],
  "privacy_security_register": [
    {{
      "obligation_type": "<privacy_policy | DPA | BAA | security | breach_notification | other>",
      "regime": "<GDPR | HIPAA | CCPA | other | null>",
      "description": "<as stated>",
      "breach_notification": "<description as stated or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote>"
    }}
  ],
  "citations": [ {{ "field", "document", "location", "quote", "confidence" }} ],
  "pass_notes": "<string or null>"
}}\
"""

_USER_PROMPT_INSURANCE = """\
COMPANY PROFILE (metadata only):
{company_profile_json}

{trigger_context}

RETRIEVED DOCUMENT CONTEXT:
{focused_chunk_text}

EXTRACTION TASK — insurance policies, coverage gaps, and unusual indemnity terms (§5.8.5).
Return ONLY this JSON object:

{{
  "insurance_register": [
    {{
      "policy_type": "<general_liability | professional | cyber | D&O | workers_comp | COI | bond | other>",
      "coverage_note": "<description as stated or null>",
      "gap_or_unusual_term_note": "<description as stated or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote>"
    }}
  ],
  "citations": [ {{ "field", "document", "location", "quote", "confidence" }} ],
  "pass_notes": "<string or null>"
}}\
"""

_DOMAIN_PASS_EXTRACT: dict[str, dict] = {
    "contracts_vendors_platform": {
        "user_prompt": _USER_PROMPT_CONTRACTS_VENDORS_PLATFORM,
        "register_keys": (
            "contract_register",
            "vendor_register",
            "platform_dependency_register",
        ),
    },
    "employment": {
        "user_prompt": _USER_PROMPT_EMPLOYMENT,
        "register_keys": ("employment_register",),
    },
    "litigation": {
        "user_prompt": _USER_PROMPT_LITIGATION,
        "register_keys": ("litigation_register",),
    },
    "ip_privacy": {
        "user_prompt": _USER_PROMPT_IP_PRIVACY,
        "register_keys": ("ip_register", "privacy_security_register"),
    },
    "insurance": {
        "user_prompt": _USER_PROMPT_INSURANCE,
        "register_keys": ("insurance_register",),
    },
}


# ---------------------------------------------------------------------------
# Domain pass registry (spec §5.6.3 / §5.11)
# ---------------------------------------------------------------------------

_DOMAIN_PASS_BUDGETS: dict[str, dict] = {
    "contracts_vendors_platform": {
        "top_k": 14,
        "min_chunk_length": 150,
        "max_chars": 20_000,
        "max_tokens": 12_000,
        # A0: broaden beyond generic MSA tokens — lease/SA/staffing dominate Elder Care LEGAL
        "file_name_filter": [
            "Contract", "MSA", "Agreement", "SOW", "Customer", "Client", "Vendor", "Supplier",
            "SA", "Lease", "Sublease", "Staffing", "Purchase", "Temp", "Marketing", "Engagement",
        ],
    },
    "employment": {
        "top_k": 10,
        "min_chunk_length": 150,
        "max_chars": 15_000,
        "max_tokens": 10_000,
        # A0: handbook/orientation/401(k) filenames — default Employment|Offer returned 0 chunks
        "file_name_filter": [
            "Employment", "Offer", "Contractor", "Commission", "Founder",
            "Handbook", "Orientation", "401", "Restricted", "Stock", "Bylaws",
        ],
    },
    "litigation": {
        "top_k": 8,
        "min_chunk_length": 150,
        "max_chars": 15_000,
        "max_tokens": 10_000,
        # A0: regulatory survey + bond filenames — default Litigation|Dispute returned 0 chunks
        "file_name_filter": [
            "Litigation", "Dispute", "Legal", "Demand", "Regulatory",
            "Survey", "DOH", "Bond", "Compliance", "Engagement",
        ],
    },
    "ip_privacy": {
        "top_k": 8,
        "min_chunk_length": 150,
        "max_chars": 15_000,
        "max_tokens": 10_000,
        "file_name_filter": [
            "IP", "Privacy", "GDPR", "HIPAA", "OSS", "Data Processing", "BAA",
        ],
    },
    "insurance": {
        "top_k": 6,
        "min_chunk_length": 150,
        "max_chars": 12_000,
        "max_tokens": 8_000,
        "file_name_filter": [
            "Insurance", "Policy", "COI", "Indemnity", "Bond", "Renewal",
        ],
    },
}

# Per-pass semantic queries — tuned from A0 corpus decomposition (§5.6.3 / B2).
_DOMAIN_PASS_QUERIES: dict[str, str] = {
    "contracts_vendors_platform": (
        "material customer contract MSA master service agreement statement of work "
        "change of control termination vendor supplier platform reseller channel "
        "staffing agreement lease sublease asset purchase marketing contract"
    ),
    "employment": (
        "employment agreement offer letter contractor commission plan founder key employee "
        "employee handbook orientation restricted stock non-compete non-solicit "
        "severance 401k bylaws staffing agreement"
    ),
    "litigation": (
        "litigation lawsuit dispute regulatory compliance arbitration demand letter "
        "settlement survey DOH approval bond renewal regulatory correspondence "
        "threatened claim legal engagement letter"
    ),
    "ip_privacy": (
        "intellectual property IP ownership assignment data privacy GDPR HIPAA "
        "indemnification liability cap open source OSS data processing agreement BAA"
    ),
    "insurance": (
        "insurance certificate policy COI certificate of insurance indemnity "
        "coverage bond renewal liability unusual indemnity"
    ),
}

# Static registry: pass_id + budget_dict per §5.11 (retrieve/extract fns bound at runtime).
_DOMAIN_PASSES: list[tuple[str, dict]] = [
    (pass_id, _DOMAIN_PASS_BUDGETS[pass_id])
    for pass_id in (
        "contracts_vendors_platform",
        "employment",
        "litigation",
        "ip_privacy",
        "insurance",
    )
]

_DOMAIN_PASS_IDS: frozenset[str] = frozenset(pass_id for pass_id, _ in _DOMAIN_PASSES)


def _has_source_doc(record: dict) -> bool:
    """True when register row carries a non-empty source_doc citation."""
    return bool(str(record.get("source_doc") or "").strip())


def _pred_t4c(merged: dict) -> bool:
    for row in merged.get("contract_register") or []:
        if not _has_source_doc(row):
            continue
        tfc = row.get("termination_for_convenience") or {}
        if not _is_not_found(tfc.get("present")):
            return True
    return False


def _pred_coc(merged: dict) -> bool:
    for row in merged.get("contract_register") or []:
        if not _has_source_doc(row):
            continue
        coc = row.get("change_of_control") or {}
        if not _is_not_found(coc.get("clause_present")):
            return True
    return False


def _pred_restrictive(merged: dict) -> bool:
    for row in merged.get("contract_register") or []:
        if not _has_source_doc(row):
            continue
        rc = row.get("restrictive_covenants") or {}
        if not _is_not_found(rc.get("present")):
            return True
    return False


def _pred_vendor(merged: dict) -> bool:
    return any(_has_source_doc(row) for row in merged.get("vendor_register") or [])


def _pred_platform(merged: dict) -> bool:
    return any(
        _has_source_doc(row) for row in merged.get("platform_dependency_register") or []
    )


def _pred_employment(merged: dict) -> bool:
    for row in merged.get("employment_register") or []:
        if not _has_source_doc(row):
            continue
        ac = row.get("agreement_class")
        if (
            _eq_str(ac, "employee")
            or _eq_str(ac, "contractor")
            or _eq_str(ac, "commission")
        ):
            return True
    return False


def _pred_founder(merged: dict) -> bool:
    for row in merged.get("employment_register") or []:
        if not _has_source_doc(row):
            continue
        if _eq_str(row.get("agreement_class"), "founder_key"):
            return True
    return False


def _pred_litigation(merged: dict) -> bool:
    return any(_has_source_doc(row) for row in merged.get("litigation_register") or [])


def _pred_privacy(merged: dict) -> bool:
    return any(
        _has_source_doc(row) for row in merged.get("privacy_security_register") or []
    )


def _pred_ip(merged: dict) -> bool:
    return any(_has_source_doc(row) for row in merged.get("ip_register") or [])


def _pred_insurance(merged: dict) -> bool:
    for row in merged.get("insurance_register") or []:
        if _has_source_doc(row):
            return True
    for reg_name in ("contract_register", "vendor_register"):
        for row in merged.get(reg_name) or []:
            liab = row.get("liability_indemnity") or {}
            if _is_true(liab.get("unusual_indemnity")):
                return True
    return False


# Normative Austin §5 gap checklist — spec §5.6 (D-M2-7: not AUSTIN_ITEM_COVERAGE).
STAKEHOLDER_COVERAGE_REQUIREMENTS: list[dict] = [
    {
        "item_id": "t4c",
        "display_name": "Customer contracts — termination for convenience",
        "assessed_predicate": _pred_t4c,
        "domain_pass_id": "contracts_vendors_platform",
        "doc_type": "Top Customer Contracts / MSAs / SOWs",
        "priority": "High",
    },
    {
        "item_id": "coc",
        "display_name": "Change-of-control clauses",
        "assessed_predicate": _pred_coc,
        "domain_pass_id": "contracts_vendors_platform",
        "doc_type": "Top Customer Contracts / MSAs / SOWs",
        "priority": "High",
    },
    {
        "item_id": "restrictive",
        "display_name": "Exclusivity, MFN, non-compete, non-solicit",
        "assessed_predicate": _pred_restrictive,
        "domain_pass_id": "contracts_vendors_platform",
        "doc_type": "Top Customer Contracts / MSAs / SOWs",
        "priority": "High",
    },
    {
        "item_id": "vendor",
        "display_name": "Vendor pricing / cancellation terms",
        "assessed_predicate": _pred_vendor,
        "domain_pass_id": "contracts_vendors_platform",
        "doc_type": "Vendor Contracts",
        "priority": "Medium",
    },
    {
        "item_id": "platform",
        "display_name": "Platform / reseller / channel dependencies",
        "assessed_predicate": _pred_platform,
        "domain_pass_id": "contracts_vendors_platform",
        "doc_type": "Referral / Channel / Platform Agreements",
        "priority": "High",
    },
    {
        "item_id": "employment",
        "display_name": "Employee, contractor, commission agreements",
        "assessed_predicate": _pred_employment,
        "domain_pass_id": "employment",
        "doc_type": "Employment Agreements",
        "priority": "Medium",
    },
    {
        "item_id": "founder",
        "display_name": "Founder / key employee agreements",
        "assessed_predicate": _pred_founder,
        "domain_pass_id": "employment",
        "doc_type": "Founder / Key Employee Agreements",
        "priority": "High",
    },
    {
        "item_id": "litigation",
        "display_name": "Litigation exposure",
        "assessed_predicate": _pred_litigation,
        "domain_pass_id": "litigation",
        "doc_type": "Litigation Summary / Legal Matters Schedule",
        "priority": "High",
    },
    {
        "item_id": "privacy",
        "display_name": "Data privacy / security obligations",
        "assessed_predicate": _pred_privacy,
        "domain_pass_id": "ip_privacy",
        "doc_type": "Privacy Policy / BAA / DPA",
        "priority": "Medium",
    },
    {
        "item_id": "ip",
        "display_name": "IP ownership, assignment, OSS",
        "assessed_predicate": _pred_ip,
        "domain_pass_id": "ip_privacy",
        "doc_type": "IP Assignment / OSS Policy",
        "priority": "Medium",
    },
    {
        "item_id": "insurance",
        "display_name": "Insurance coverage gaps",
        "assessed_predicate": _pred_insurance,
        "domain_pass_id": "insurance",
        "doc_type": "Insurance Certificates / Policies",
        "priority": "Medium",
    },
]

assert len(STAKEHOLDER_COVERAGE_REQUIREMENTS) == 11
assert all(
    req["domain_pass_id"] in _DOMAIN_PASS_IDS
    for req in STAKEHOLDER_COVERAGE_REQUIREMENTS
)


def _bind_domain_passes(agent: "LegalContractsAgent") -> list[tuple]:
    """Materialize full _DOMAIN_PASSES tuples with bound instance methods."""
    return [
        (
            pass_id,
            getattr(agent, f"_domain_retrieve_{pass_id}"),
            getattr(agent, f"_extract_{pass_id}"),
            budget,
        )
        for pass_id, budget in _DOMAIN_PASSES
    ]


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

from agents.shared.agent_base import WorkstreamAgent


class LegalContractsAgent(WorkstreamAgent):
    """Phase 3 Legal & Contracts workstream agent."""

    agent_name = "legal_contracts"

    def __init__(self):
        super().__init__()

    def _log_no_flag(self, metric: str, value_str: str, threshold: str, note: str = ""):
        """Log a threshold evaluation that did NOT trigger a flag."""
        step = len(self._trace) + 1
        self._trace.append({
            "step":       step,
            "tool":       "threshold_evaluation",
            "input":      f"metric={metric}, value={value_str}, threshold={threshold}",
            "output":     f"No flag triggered — {note}" if note else "No flag triggered",
            "confidence": "high",
            "sources":    [],
        })
        print(f"  Step {step} [threshold_evaluation]: {metric}={value_str} vs {threshold} → no flag")

    def _load_contract_triggers(self, company_name: str, spark) -> list:
        """Load contract review triggers from Customer Quality Agent output.

        Returns list of trigger dicts. Returns empty list if table not found or
        Customer Quality Agent has not yet run — graceful fallback so this agent
        can produce output independently.
        """
        try:
            rows = spark.sql(f"""
                SELECT contract_trigger_list FROM {self._catalog}.analysis.customer_quality
                WHERE company_name = '{company_name}'
                ORDER BY created_at DESC LIMIT 1
            """).collect()
            if rows and rows[0]["contract_trigger_list"]:
                return [json.loads(t) for t in rows[0]["contract_trigger_list"]]
        except Exception:
            pass
        self._add_gap(
            "contract_trigger_list not found — Customer Quality Agent has not run or "
            "returned no material customers. Legal Agent proceeding without triggered reviews."
        )
        return []

    # -----------------------------------------------------------------------
    # Retrieval tools
    # -----------------------------------------------------------------------

    def _tool_load_company_profile(self, company_name: str, spark) -> "ToolResult":  # noqa: F821
        try:
            rows = spark.sql(
                f"SELECT * FROM {self._catalog}.classification.company_profile "
                f"WHERE company_name = '{company_name}' "
                f"ORDER BY created_at DESC LIMIT 1"
            ).collect()
            if not rows:
                self._add_gap("company_profile not found — run company_profiler.py first")
                return self._tool_call(
                    tool_name="load_company_profile",
                    input_summary=f"SELECT * FROM {self._catalog}.classification.company_profile WHERE company_name='{company_name}'",
                    data=None,
                    output_summary="No rows returned — company_profile not found",
                    confidence="low",
                    source_docs=[],
                )
            row_dict = rows[0].asDict()
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"SELECT * FROM {self._catalog}.classification.company_profile WHERE company_name='{company_name}'",
                data=row_dict,
                output_summary=f"Company profile loaded for '{company_name}'",
                confidence="high",
                source_docs=[f"{self._catalog}.classification.company_profile"],
            )
        except Exception as exc:
            self._add_gap(f"company_profile query failed: {exc} — run company_profiler.py first")
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"SELECT * FROM {self._catalog}.classification.company_profile WHERE company_name='{company_name}'",
                data=None,
                output_summary=f"Query failed: {exc}",
                confidence="low",
                source_docs=[],
            )

    # -----------------------------------------------------------------------
    # Domain pass retrieval (B2 — D3a catalog-threaded fallback)
    # -----------------------------------------------------------------------

    def _semantic_search_with_fallback(
        self,
        spark,
        query: str,
        workstream_filter: list,
        top_k: int,
        file_name_filter,
        min_chunk_length: int = 150,
        min_results: int = 3,
    ) -> list:
        """Semantic search with filename-filter retry; always passes catalog=self._catalog (D3a).

        Do not use the financial context_utils fallback helper — it defaults catalog to uc13.
        """
        from agents.shared.retrieval import semantic_search

        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=top_k,
            workstream_filter=workstream_filter,
            file_name_filter=file_name_filter,
            min_chunk_length=min_chunk_length,
            catalog=self._catalog,
        )

        if len(chunks) < min_results and file_name_filter is not None:
            step = len(self._trace) + 1
            self._trace.append({
                "step":       step,
                "tool":       "retrieval_fallback",
                "input":      (
                    f"file_name_filter returned {len(chunks)} chunks (< {min_results}); "
                    f"retrying without filter"
                ),
                "output":     "fallback retrieval active — all workstream-tagged documents searched",
                "confidence": "medium",
                "sources":    [],
            })
            print(
                f"  Step {step} [retrieval_fallback]: filter returned {len(chunks)} chunks, "
                f"retrying without filename filter"
            )
            chunks = semantic_search(
                query=query,
                spark=spark,
                company_name=self._company_name,
                top_k=top_k,
                workstream_filter=workstream_filter,
                file_name_filter=None,
                min_chunk_length=min_chunk_length,
                catalog=self._catalog,
            )

        return chunks

    def _domain_retrieve_pass(self, spark, pass_id: str) -> "ToolResult":  # noqa: F821
        """Run semantic retrieval for one domain pass using §5.6.3 budgets."""
        budget = _DOMAIN_PASS_BUDGETS[pass_id]
        query = _DOMAIN_PASS_QUERIES[pass_id]
        file_name_filter = budget["file_name_filter"]
        filter_preview = ", ".join(file_name_filter[:6])
        if len(file_name_filter) > 6:
            filter_preview += ", …"

        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=query,
            workstream_filter=["LEGAL"],
            top_k=budget["top_k"],
            file_name_filter=file_name_filter,
            min_chunk_length=budget["min_chunk_length"],
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name=f"domain_retrieve_{pass_id}",
            input_summary=(
                f"pass={pass_id} | workstream=LEGAL | top_k={budget['top_k']} | "
                f"file_name_filter=[{filter_preview}]"
            ),
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _domain_retrieve_contracts_vendors_platform(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "contracts_vendors_platform")

    def _domain_retrieve_employment(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "employment")

    def _domain_retrieve_litigation(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "litigation")

    def _domain_retrieve_ip_privacy(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "ip_privacy")

    def _domain_retrieve_insurance(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "insurance")

    # -----------------------------------------------------------------------
    # Domain pass extract (B3 — per-pass LLM extraction)
    # -----------------------------------------------------------------------

    def _build_trigger_context(self, pass_id: str, contract_triggers: list) -> str:
        """Inject read-only CQA trigger context where relevant (D8a)."""
        if pass_id != "contracts_vendors_platform" or not contract_triggers:
            return ""
        trigger_json = json.dumps(contract_triggers, indent=2, default=str)
        return (
            "CONTRACT REVIEW TRIGGERS (from Customer Quality Agent — prioritize these "
            f"counterparties when extracting contracts):\n{trigger_json}\n"
        )

    def _ingest_pass_citations(self, citations: list) -> None:
        for cite in citations or []:
            if not isinstance(cite, dict):
                continue
            self._add_citation(
                claim=cite.get("field", ""),
                document=cite.get("document", ""),
                location=cite.get("location", ""),
                confidence=cite.get("confidence", "medium"),
                raw_text=cite.get("quote", ""),
            )

    def _empty_pass_registers(self, pass_id: str) -> dict:
        return {key: [] for key in _DOMAIN_PASS_EXTRACT[pass_id]["register_keys"]}

    def _normalize_pass_payload(self, pass_id: str, parsed: dict) -> dict:
        """Ensure all §5.8 register keys exist; drop unknown top-level keys."""
        register_keys = _DOMAIN_PASS_EXTRACT[pass_id]["register_keys"]
        return {
            key: parsed.get(key) if isinstance(parsed.get(key), list) else []
            for key in register_keys
        }

    def _domain_extract_pass(
        self,
        pass_id: str,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        """Run build_focused_context → _call_llm → _parse_json_response for one pass."""
        import importlib

        context_utils = importlib.import_module(
            "agents.subagents.workstream.financial.context_utils"
        )
        build_focused_context = context_utils.build_focused_context

        tool_name = f"domain_extract_{pass_id}"
        empty = self._empty_pass_registers(pass_id)
        register_keys = _DOMAIN_PASS_EXTRACT[pass_id]["register_keys"]
        user_template = _DOMAIN_PASS_EXTRACT[pass_id]["user_prompt"]
        max_chars = budget["max_chars"]
        max_tokens = budget["max_tokens"]

        if not chunks:
            summary = ", ".join(f"{k}=0" for k in register_keys)
            self._tool_call(
                tool_name=tool_name,
                input_summary=f"pass={pass_id} | 0 chunks — skipped LLM",
                data=None,
                output_summary=summary,
                confidence="low",
                source_docs=[],
            )
            return empty

        trigger_context = self._build_trigger_context(pass_id, contract_triggers)
        company_profile_json = json.dumps(company_profile or {}, default=str)
        source_docs = list({getattr(c, "file_name", "") for c in chunks if getattr(c, "file_name", "")})

        parsed = None
        context_stats = ""
        failure_note = ""
        char_budgets = [max_chars, max(max_chars // 2, 4_000)]

        for attempt, chars_budget in enumerate(char_budgets):
            try:
                context_text, context_stats = build_focused_context(chunks, max_chars=chars_budget)
                user_prompt = user_template.format(
                    company_profile_json=company_profile_json,
                    trigger_context=trigger_context,
                    focused_chunk_text=context_text,
                )
                raw = self._call_llm(
                    _EXTRACT_SYSTEM_PROMPT,
                    user_prompt,
                    extraction_endpoint,
                    max_tokens=max_tokens,
                )
                parsed = self._parse_json_response(raw)
                break
            except ValueError as exc:
                failure_note = str(exc)
                if attempt == 0:
                    self._add_gap(
                        f"{pass_id}: LLM JSON parse failed — retrying with halved context "
                        f"({chars_budget} → {char_budgets[1]} chars)"
                    )
                    continue
                break
            except Exception as exc:
                failure_note = str(exc)
                break

        if parsed is None:
            summary = ", ".join(f"{k}=0" for k in register_keys)
            self._tool_call(
                tool_name=tool_name,
                input_summary=(
                    f"pass={pass_id} | {len(chunks)} chunks | context: {context_stats or 'n/a'} | "
                    f"extraction failed"
                ),
                data=None,
                output_summary=f"{summary} — {failure_note[:120]}" if failure_note else summary,
                confidence="low",
                source_docs=source_docs,
            )
            return empty

        normalized = self._normalize_pass_payload(pass_id, parsed)
        self._ingest_pass_citations(parsed.get("citations"))

        counts = ", ".join(f"{k}={len(normalized[k])}" for k in register_keys)
        pass_notes = parsed.get("pass_notes")
        output_summary = counts
        if pass_notes:
            output_summary += f" | pass_notes: {str(pass_notes)[:80]}"

        self._tool_call(
            tool_name=tool_name,
            input_summary=(
                f"pass={pass_id} | {len(chunks)} chunks | context: {context_stats} | "
                f"max_tokens={max_tokens}"
            ),
            data=normalized,
            output_summary=output_summary,
            confidence="high" if any(normalized[k] for k in register_keys) else "medium",
            source_docs=source_docs,
        )
        return normalized

    def _extract_contracts_vendors_platform(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        return self._domain_extract_pass(
            "contracts_vendors_platform",
            chunks,
            company_profile,
            contract_triggers,
            extraction_endpoint,
            budget,
        )

    def _extract_employment(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        return self._domain_extract_pass(
            "employment",
            chunks,
            company_profile,
            contract_triggers,
            extraction_endpoint,
            budget,
        )

    def _extract_litigation(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        return self._domain_extract_pass(
            "litigation",
            chunks,
            company_profile,
            contract_triggers,
            extraction_endpoint,
            budget,
        )

    def _extract_ip_privacy(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        return self._domain_extract_pass(
            "ip_privacy",
            chunks,
            company_profile,
            contract_triggers,
            extraction_endpoint,
            budget,
        )

    def _extract_insurance(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        return self._domain_extract_pass(
            "insurance",
            chunks,
            company_profile,
            contract_triggers,
            extraction_endpoint,
            budget,
        )

    # -----------------------------------------------------------------------
    # Post-loop register merge (spec §5.6.2)
    # -----------------------------------------------------------------------

    def _merge_registers(self, registers: dict[str, list]) -> dict[str, list]:
        """Within-register dedupe after per-pass extend; no cross-register merge."""
        merged: dict[str, list] = {}
        dedupe_stats: dict[str, dict] = {}
        merge_notes: list[str] = []

        for register_name, rows in registers.items():
            if not rows:
                merged[register_name] = []
                dedupe_stats[register_name] = {"input": 0, "output": 0, "collisions": 0}
                continue

            by_key: dict[tuple, dict] = {}
            collisions = 0
            for row in rows:
                key = _register_dedupe_key(register_name, row)
                if key in by_key:
                    collisions += 1
                    merge_notes.append(
                        f"{register_name}: merged duplicate key {key!r} "
                        f"(kept longer raw_quote)"
                    )
                    by_key[key] = _merge_register_records(by_key[key], row)
                else:
                    by_key[key] = dict(row)

            merged[register_name] = list(by_key.values())
            dedupe_stats[register_name] = {
                "input": len(rows),
                "output": len(merged[register_name]),
                "collisions": collisions,
            }

        step = len(self._trace) + 1
        summary = ", ".join(
            f"{name}={stats['input']}→{stats['output']}"
            for name, stats in sorted(dedupe_stats.items())
        )
        self._trace.append({
            "step":       step,
            "tool":       "merge_registers",
            "input":      f"registers pre-merge ({summary})",
            "output":     json.dumps(dedupe_stats),
            "confidence": "high",
            "sources":    [],
        })
        if merge_notes:
            note_step = len(self._trace) + 1
            self._trace.append({
                "step":       note_step,
                "tool":       "merge_registers",
                "input":      "within-register dedupe collisions",
                "output":     "; ".join(merge_notes[:20]),
                "confidence": "high",
                "sources":    [],
            })
        print(f"  Step {step} [merge_registers]: {summary}")
        return merged

    # -----------------------------------------------------------------------
    # Roll-up computations (deterministic Python — no LLM)
    # -----------------------------------------------------------------------

    def _build_coc_consent_list(self, contract_register: list) -> list:
        """All contracts where change_of_control.consent_required is tri-state true."""
        return [
            {
                "contract_id": c.get("contract_id"),
                "counterparty_name": c.get("counterparty_name"),
                "revenue_pct": c.get("revenue_pct"),
                "consent_standard_note": c.get("change_of_control", {}).get("consent_standard"),
            }
            for c in contract_register
            if _is_true(c.get("change_of_control", {}).get("consent_required"))
        ]

    def _build_termination_exposure(self, contract_register: list) -> list:
        """Contracts with termination for convenience AND notice < 90 days."""
        result = []
        for c in contract_register:
            tfc = c.get("termination_for_convenience", {})
            if not _is_true(tfc.get("present")):
                continue
            notice = _parse_int(tfc.get("notice_days"))
            if notice is not None and notice < 90:
                result.append({
                    "contract_id": c.get("contract_id"),
                    "counterparty_name": c.get("counterparty_name"),
                    "notice_days": notice,
                    "revenue_pct": c.get("revenue_pct"),
                })
        return result

    def _build_restrictive_covenant_map(self, contract_register: list) -> list:
        return [
            {
                "contract_id": c.get("contract_id"),
                "counterparty_name": c.get("counterparty_name"),
                "scope_note": c.get("restrictive_covenants", {}).get("scope_note"),
            }
            for c in contract_register
            if _is_true(c.get("restrictive_covenants", {}).get("present"))
        ]

    # -----------------------------------------------------------------------
    # Stakeholder coverage gaps + section confidence (spec §5.6)
    # -----------------------------------------------------------------------

    @staticmethod
    def _is_healthcare_overlay(company_profile: dict | None) -> bool:
        """Normalize healthcare overlay — profile may emit healthcare or healthcare_services."""
        overlay = str((company_profile or {}).get("industry_overlay") or "").strip().lower()
        return overlay in ("healthcare_services", "healthcare")

    def _assess_coverage_gaps(
        self,
        merged: dict,
        pass_chunk_counts: dict[str, int],
        company_profile: dict | None,
    ) -> None:
        """Evaluate STAKEHOLDER_COVERAGE_REQUIREMENTS; stage gap JSON lists for T4 return.

        pass_chunk_counts: ``pass_id → len(chunks)`` recorded in the run() domain loop (D-M2-2).
        T4 populates this dict each iteration before calling this method post-merge.
        """
        self._unable_to_assess_items: list[str] = []
        self._recommended_diligence: list[dict] = []
        assessed_count = 0

        for req in STAKEHOLDER_COVERAGE_REQUIREMENTS:
            item_id = req["item_id"]
            if req["assessed_predicate"](merged):
                assessed_count += 1
                continue

            pass_id = req["domain_pass_id"]
            chunk_count = pass_chunk_counts.get(pass_id, 0)

            if chunk_count >= 1:
                self._add_gap(f"{item_id}: chunks retrieved but no extractable terms")
                self._unable_to_assess_items.append(req["display_name"])
            else:
                self._add_gap(
                    f"{item_id}: no documents retrieved for {pass_id} pass — "
                    f"request {req['doc_type']}"
                )
                self._unable_to_assess_items.append(req["display_name"])
                self._recommended_diligence.append({
                    "doc_type": req["doc_type"],
                    "priority": req["priority"],
                    "item_id": item_id,
                })

        if self._is_healthcare_overlay(company_profile):
            self._recommended_diligence.append({
                "doc_type": "Healthcare Referral Agreements",
                "priority": "High",
                "item_id": "healthcare_referral",
            })

        self._assessed_coverage_count = assessed_count

        step = len(self._trace) + 1
        self._trace.append({
            "step":       step,
            "tool":       "assess_coverage_gaps",
            "input":      (
                f"checklist={len(STAKEHOLDER_COVERAGE_REQUIREMENTS)} items | "
                f"pass_chunk_counts={pass_chunk_counts}"
            ),
            "output":     (
                f"assessed={assessed_count} | unable={len(self._unable_to_assess_items)} | "
                f"diligence={len(self._recommended_diligence)}"
            ),
            "confidence": "high",
            "sources":    [],
        })
        print(
            f"  Step {step} [assess_coverage_gaps]: assessed={assessed_count}/11, "
            f"unable={len(self._unable_to_assess_items)}, "
            f"diligence={len(self._recommended_diligence)}"
        )

    def _compute_section_confidence(self) -> str:
        """Map assessed checklist count (0–11) to low / medium / high — spec §5.6."""
        count = getattr(self, "_assessed_coverage_count", 0)
        if count <= 2:
            return "low"
        if count <= 6:
            return "medium"
        return "high"

    # -----------------------------------------------------------------------
    # Threshold flagging
    # -----------------------------------------------------------------------

    def _apply_legal_flags(self, merged: dict) -> None:
        """Option-C MVP flags per spec §5.6 — scans merged registers post-dedupe."""
        contract_register = merged.get("contract_register") or []
        vendor_register = merged.get("vendor_register") or []
        litigation_register = merged.get("litigation_register") or []

        for c in contract_register:
            cpname = c.get("counterparty_name", "")
            source_doc = c.get("source_doc", "")

            coc = c.get("change_of_control", {})
            if _is_true(coc.get("consent_required")):
                self._add_flag(
                    metric="coc_consent_required",
                    value=f"{cpname} — CoC consent required",
                    threshold="Any CoC consent required",
                    severity="Red",
                    note=(
                        f"CoC consent required for {cpname}. "
                        f"Deal-relevant — obtain consent pre-close. "
                        f"Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )

            rc = c.get("restrictive_covenants", {})
            if _is_true(rc.get("present")):
                scope = rc.get("scope_note") or "scope not stated"
                self._add_flag(
                    metric="restrictive_covenant",
                    value=f"{cpname}: {scope}",
                    threshold="Restrictive covenant present",
                    severity="Yellow",
                    note=(
                        f"Restrictive covenant ({scope}) in {cpname} contract. "
                        f"May limit add-on M&A options. Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )

            liab = c.get("liability_indemnity", {})
            if _is_true(liab.get("unusual_indemnity")):
                self._add_flag(
                    metric="unusual_indemnity",
                    value=f"{cpname} — unusual_indemnity=true",
                    threshold="Unusual indemnity scope",
                    severity="Yellow",
                    note=(
                        f"Unusual indemnity scope in {cpname} contract. "
                        f"Refer to outside counsel for assessment. Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="medium",
                )

        for v in vendor_register:
            vname = v.get("vendor_name", "")
            source_doc = v.get("source_doc", "")
            liab = v.get("liability_indemnity", {})
            if _is_true(liab.get("unusual_indemnity")):
                self._add_flag(
                    metric="unusual_indemnity",
                    value=f"{vname} — unusual_indemnity=true",
                    threshold="Unusual indemnity scope",
                    severity="Yellow",
                    note=(
                        f"Unusual indemnity scope in {vname} vendor agreement. "
                        f"Refer to outside counsel for assessment. Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="medium",
                )

        for item in litigation_register:
            matter_type = item.get("matter_type", "unknown")
            description = item.get("description", "")
            source_doc = item.get("source_doc", "")
            status = item.get("status")

            if _eq_str(status, "open"):
                self._add_flag(
                    metric=f"open_legal_matter_{matter_type}",
                    value=f"{matter_type}: {description[:80]}",
                    threshold="Any open legal matter",
                    severity="Red",
                    note=(
                        f"Open legal matter ({matter_type}): {description[:200]}. "
                        f"Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )

            if _eq_str(matter_type, "regulatory"):
                self._add_flag(
                    metric="regulatory_matter",
                    value=f"regulatory: {description[:80]}",
                    threshold="Any regulatory matter (regardless of status)",
                    severity="Red",
                    note=(
                        f"Regulatory matter (status={status}): {description[:200]}. "
                        f"Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )

    # -----------------------------------------------------------------------
    # run()
    # -----------------------------------------------------------------------

    def run(self, company_name: str, spark, extraction_endpoint: str, catalog: str) -> dict:
        self._reset_state()
        self._company_name = company_name
        self._catalog = catalog

        # Stage 1 — company profile + contract triggers (D8a: read-only triggers)
        print(f"  Loading contract triggers ...")
        contract_triggers = self._load_contract_triggers(company_name, spark)

        print(f"  Loading company profile ...")
        profile_result = self._tool_load_company_profile(company_name, spark)
        company_profile = profile_result.data

        # Pass-owned register accumulators (M1 interim — no cross-pass merge)
        registers: dict[str, list] = {
            "contract_register": [],
            "vendor_register": [],
            "platform_dependency_register": [],
            "employment_register": [],
            "litigation_register": [],
            "ip_register": [],
            "privacy_security_register": [],
            "insurance_register": [],
        }

        domain_passes = _bind_domain_passes(self)
        print(f"  Running {len(domain_passes)} domain passes ...")
        for pass_id, retrieve_fn, extract_fn, budget in domain_passes:
            retrieve_result = retrieve_fn(spark)
            chunks = retrieve_result.data or []
            print(f"    [{pass_id}] retrieve: {len(chunks)} chunks")

            extracted = extract_fn(
                chunks,
                company_profile,
                contract_triggers,
                extraction_endpoint,
                budget,
            )
            for key, rows in extracted.items():
                if key in registers and rows:
                    registers[key].extend(rows)

            register_summary = ", ".join(
                f"{k}={len(extracted.get(k, []))}"
                for k in sorted(extracted.keys())
            )
            print(f"    [{pass_id}] extract: {register_summary}")

        return {
            "company_name":                       company_name,
            "executive_summary":                  None,
            "contract_register_json":             json.dumps(registers["contract_register"]),
            "vendor_register_json":               json.dumps(registers["vendor_register"]),
            "platform_dependency_register_json":  json.dumps(registers["platform_dependency_register"]),
            "employment_register_json":           json.dumps(registers["employment_register"]),
            "litigation_register_json":           json.dumps(registers["litigation_register"]),
            "ip_register_json":                   json.dumps(registers["ip_register"]),
            "privacy_security_register_json":     json.dumps(registers["privacy_security_register"]),
            "insurance_register_json":            json.dumps(registers["insurance_register"]),
            "coc_consent_list_json":              json.dumps([]),
            "termination_exposure_json":          json.dumps([]),
            "restrictive_covenant_map_json":      json.dumps([]),
            "triggered_reviews_loaded":           len(contract_triggers),
            "flags":                              [],
            "data_room_gaps":                     list(self._data_room_gaps),
            "citations":                          json.dumps(self._citations_as_dicts()),
            "reasoning_trace":                    list(self._trace),
            "created_at":                         datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Stakeholder report export
# ---------------------------------------------------------------------------

def _write_stakeholder_report(result: dict, catalog: str, spark) -> str:
    """Write a clean, human-readable YAML report to a UC Volume.

    Saves to /Volumes/{catalog}/analysis/reports/{company_name}/
    legal_contracts_report.yaml (or .json if PyYAML is unavailable).
    Returns the full volume path of the written file.
    """
    company_name = result["company_name"]

    contract_register   = json.loads(result.get("contract_register_json")        or "[]")
    litigation_register = json.loads(result.get("litigation_register_json")       or "[]")
    coc_consent_list    = json.loads(result.get("coc_consent_list_json")          or "[]")
    termination_exp     = json.loads(result.get("termination_exposure_json")      or "[]")
    covenant_map        = json.loads(result.get("restrictive_covenant_map_json")  or "[]")
    citations           = json.loads(result.get("citations")                      or "[]")

    report = {
        "report": {
            "agent":        "legal_contracts",
            "company":      company_name,
            "generated_at": result.get("created_at", ""),
        },
        "executive_summary":       result.get("executive_summary"),
        "contract_register":       contract_register,
        "coc_consent_list":        coc_consent_list,
        "termination_exposure":    termination_exp,
        "restrictive_covenant_map": covenant_map,
        "litigation_register":     litigation_register,
        "triggered_reviews_loaded": result.get("triggered_reviews_loaded", 0),
        "flags":                   result.get("flags") or [],
        "data_room_gaps":          result.get("data_room_gaps") or [],
        "citations":               citations,
    }

    try:
        import yaml

        def _str_representer(dumper, data):
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        yaml.add_representer(str, _str_representer)
        content = yaml.dump(report, allow_unicode=True, sort_keys=False, width=120)
        ext = "yaml"
    except ImportError:
        content = json.dumps(report, indent=2, ensure_ascii=False)
        ext = "json"

    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
    safe_name = company_name.replace(" ", "_").replace("/", "_")
    dir_path = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
    os.makedirs(dir_path, exist_ok=True)

    file_path = f"{dir_path}/legal_contracts_report.{ext}"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return file_path


# ---------------------------------------------------------------------------
# Delta table DDL — Appendix A (legal_agent.md v0.2.2)
# ---------------------------------------------------------------------------

_EXPECTED_COLS = {
    "company_name",
    "executive_summary",
    "section_confidence",
    "contract_register_json",
    "vendor_register_json",
    "platform_dependency_register_json",
    "employment_register_json",
    "litigation_register_json",
    "privacy_security_register_json",
    "ip_register_json",
    "insurance_register_json",
    "coc_consent_list_json",
    "termination_exposure_json",
    "restrictive_covenant_map_json",
    "unable_to_assess_json",
    "recommended_diligence_json",
    "flags",
    "data_room_gaps",
    "citations",
    "reasoning_trace",
    "created_at",
}

_CREATE_LEGAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {catalog}.analysis.legal (
    company_name                          STRING,
    executive_summary                     STRING,
    section_confidence                    STRING,
    contract_register_json                STRING,
    vendor_register_json                  STRING,
    platform_dependency_register_json     STRING,
    employment_register_json              STRING,
    litigation_register_json              STRING,
    privacy_security_register_json        STRING,
    ip_register_json                      STRING,
    insurance_register_json               STRING,
    coc_consent_list_json                 STRING,
    termination_exposure_json             STRING,
    restrictive_covenant_map_json         STRING,
    unable_to_assess_json                 STRING,
    recommended_diligence_json            STRING,
    flags                                 STRING,
    data_room_gaps                        ARRAY<STRING>,
    citations                             STRING,
    reasoning_trace                       STRING,
    created_at                            TIMESTAMP
) USING DELTA
"""

_CREATE_LEGAL_CONTRACTS_VIEW_SQL = """
CREATE OR REPLACE VIEW {catalog}.analysis.legal_contracts AS
SELECT
  company_name, executive_summary,
  contract_register_json, litigation_register_json,
  coc_consent_list_json, termination_exposure_json, restrictive_covenant_map_json,
  0 AS triggered_reviews_loaded,
  flags, data_room_gaps, citations, reasoning_trace, created_at
FROM {catalog}.analysis.legal
"""


def _map_legacy_result_to_legal_row(result: dict) -> dict:
    """Map legacy run() output to analysis.legal row; MVP-only columns get empty JSON."""
    return {
        "company_name":                  result["company_name"],
        "executive_summary":             result.get("executive_summary"),
        "section_confidence":            None,
        "contract_register_json":             result.get("contract_register_json"),
        "vendor_register_json":               result.get("vendor_register_json", "[]"),
        "platform_dependency_register_json":  result.get("platform_dependency_register_json", "[]"),
        "employment_register_json":           result.get("employment_register_json", "[]"),
        "litigation_register_json":           result.get("litigation_register_json"),
        "privacy_security_register_json":     result.get("privacy_security_register_json", "[]"),
        "ip_register_json":                   result.get("ip_register_json", "[]"),
        "insurance_register_json":            result.get("insurance_register_json", "[]"),
        "coc_consent_list_json":         result.get("coc_consent_list_json"),
        "termination_exposure_json":     result.get("termination_exposure_json"),
        "restrictive_covenant_map_json": result.get("restrictive_covenant_map_json"),
        "unable_to_assess_json":         "[]",
        "recommended_diligence_json":    "[]",
        "flags":                         json.dumps(result.get("flags") or []),
        "data_room_gaps":                result.get("data_room_gaps") or [],
        "citations":                     result.get("citations"),
        "reasoning_trace":               json.dumps(result.get("reasoning_trace") or []),
        "created_at":                    datetime.now(timezone.utc),
    }


def _ensure_legal_storage(catalog: str, spark) -> None:
    """Idempotent Appendix A DDL: analysis.legal table + legal_contracts compat view."""
    legal_table = f"{catalog}.analysis.legal"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

    try:
        live_cols = {f.name for f in spark.table(legal_table).schema.fields}
        if not _EXPECTED_COLS.issubset(live_cols):
            missing = _EXPECTED_COLS - live_cols
            print(f"  [schema_migration] {legal_table}: dropping stale table. Missing: {sorted(missing)}")
            spark.sql(f"DROP TABLE IF EXISTS {legal_table}")
    except Exception:
        pass

    spark.sql(_CREATE_LEGAL_TABLE_SQL.format(catalog=catalog))
    spark.sql(f"DROP TABLE IF EXISTS {catalog}.analysis.legal_contracts")
    spark.sql(_CREATE_LEGAL_CONTRACTS_VIEW_SQL.format(catalog=catalog))


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main() -> dict:
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    company_name        = get_param("sp_company_name")
    catalog             = get_param("catalog",             default="uc13_ale")
    _widget_ep          = get_param("extraction_endpoint", default="databricks-claude-sonnet-4-6") or "databricks-claude-sonnet-4-6"
    llm_endpoint        = get_param("llm_endpoint",        default=_widget_ep)

    if "haiku" in _widget_ep.lower() or "llama" in _widget_ep.lower():
        extraction_endpoint = "databricks-claude-sonnet-4-6"
        print(f"  [override] extraction_endpoint '{_widget_ep}' → Sonnet (Haiku/Llama cap=8192 tokens; legal multi-pass schema needs Sonnet)")
    else:
        extraction_endpoint = _widget_ep

    from pyspark.sql import SparkSession
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Legal Contracts Agent ({company_name}) ===")
    print(f"  catalog={catalog}  extraction_endpoint={extraction_endpoint}  llm_endpoint={llm_endpoint}")
    print(f"  write target={catalog}.analysis.legal")

    _ensure_legal_storage(catalog, spark)

    agent = LegalContractsAgent()
    result = agent.run(
        company_name=company_name,
        spark=spark,
        extraction_endpoint=extraction_endpoint,
        catalog=catalog,
    )

    table = f"{catalog}.analysis.legal"
    spark.sql(f"DELETE FROM {table} WHERE company_name = '{company_name}'")

    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType,
        ArrayType, TimestampType,
    )

    schema = StructType([
        StructField("company_name",                          StringType(),            True),
        StructField("executive_summary",                     StringType(),            True),
        StructField("section_confidence",                    StringType(),            True),
        StructField("contract_register_json",                StringType(),            True),
        StructField("vendor_register_json",                  StringType(),            True),
        StructField("platform_dependency_register_json",     StringType(),            True),
        StructField("employment_register_json",              StringType(),            True),
        StructField("litigation_register_json",              StringType(),            True),
        StructField("privacy_security_register_json",        StringType(),            True),
        StructField("ip_register_json",                      StringType(),            True),
        StructField("insurance_register_json",               StringType(),            True),
        StructField("coc_consent_list_json",                 StringType(),            True),
        StructField("termination_exposure_json",             StringType(),            True),
        StructField("restrictive_covenant_map_json",         StringType(),            True),
        StructField("unable_to_assess_json",                 StringType(),            True),
        StructField("recommended_diligence_json",            StringType(),            True),
        StructField("flags",                                 StringType(),            True),
        StructField("data_room_gaps",                        ArrayType(StringType()), True),
        StructField("citations",                             StringType(),            True),
        StructField("reasoning_trace",                       StringType(),            True),
        StructField("created_at",                            TimestampType(),         True),
    ])

    row_data = _map_legacy_result_to_legal_row(result)

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").saveAsTable(table)

    print(f"\n✓ Saved legal output → {table}")

    report_path = _write_stakeholder_report(result, catalog, spark)
    result["report_path"] = report_path
    print(f"✓ Stakeholder report → {report_path}")

    return result


if __name__ == "__main__":
    main()
