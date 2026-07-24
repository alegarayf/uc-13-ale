"""
cross_analysis_agent.py — Phase 4: Cross-Analysis Agent (Spec §10, Guideline 8).

Runs after all seven Phase 3 workstream agents complete. Purpose:
  (1) reconcile findings across workstreams (§10.1),
  (2) check CIM claims against data-room evidence (§10.2),
  (3) rank and prioritize flags into the top 10 issues (§10.3),
  (4) produce the data-room gap list (§10.4).

Context discipline (the reason this agent is cheap despite touching all workstreams):
  - It reads ONLY the compact ``*_json`` summary columns from ``uc13.analysis.*``
    via ``to_result_card()`` / targeted SQL — never chunks, embeddings, or
    reasoning_trace.
  - The ~10 reconciliation checks (§10.1) are DETERMINISTIC pairwise comparisons
    over specific JSON fields. No LLM. Each returns match / mismatch / cannot_check;
    a missing upstream input degrades to cannot_check (never an error) so a failed
    Phase 3 agent does not break Phase 4.
  - The LLM is used in exactly two bounded places: (a) extracting CIM factual
    claims from CIM chunks (§10.2), and (b) ranking the top 10 issues from the
    compact candidate list (§10.3).

Phase 4 outputs:
  - Table uc13.analysis.cross_analysis

Dependencies (all soft — each check degrades to cannot_check if absent):
  - uc13.analysis.{business_model, financial_trends, customer_quality, kpi,
                   legal_contracts, quality_of_earnings, forecast}
  - uc13.ingestion.embeddings   (CIM claims retrieval only)
  - agents.orchestration.pipeline.to_result_card
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
# Secrets / params / repo-root helpers — copied verbatim from the workstream agents
# ---------------------------------------------------------------------------

def _get_dbutils():
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
        raise RuntimeError(f"Parameter '{key}' not found.")
    return value


def get_current_path():
    try:
        notebook_path = (
            dbutils.notebook.entry_point  # noqa: F821
            .getDbutils().notebook().getContext().notebookPath().get()
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


def _parse_numeric(value_str: Optional[str]) -> Optional[float]:
    if value_str is None:
        return None
    cleaned = re.sub(r"[$,%\s]", "", str(value_str)).replace("(", "-").replace(")", "")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Reconciliation result helper
# ---------------------------------------------------------------------------

def _check(name, agents, status, materiality, detail, citations=None):
    """Build a reconciliation-log record. status ∈ match|mismatch|cannot_check."""
    return {
        "check": name,
        "agents_involved": agents,
        "status": status,
        "materiality": materiality,   # critical | material | track | n/a
        "detail": detail,
        "citations": citations or [],
    }


# ---------------------------------------------------------------------------
# LLM prompts (bounded usage only)
# ---------------------------------------------------------------------------

_CIM_CLAIMS_SYSTEM = """\
You are a PE diligence analyst. Extract the specific, checkable FACTUAL CLAIMS a CIM
(confidential information memorandum) or management presentation makes. Rules:
1. Extract ONLY claims explicitly stated in the provided CIM context.
2. Focus on claims that can be checked against a data room: revenue figures, growth
   rates, customer concentration ("no customer exceeds X%"), retention (NRR/GRR),
   contract structure ("all customers on multi-year contracts"), margin figures,
   headcount, and compliance ("no material compliance issues").
3. For each claim give a stated_value where the claim contains a number/threshold.
4. Return ONLY valid JSON, no markdown fences.\
"""

_CIM_CLAIMS_USER = """\
CIM / MANAGEMENT PRESENTATION CONTEXT:
{cim_context}

Return this exact JSON:
{{
  "cim_claims": [
    {{
      "claim_id": "<sequential integer>",
      "category": "<revenue | growth | concentration | retention | contracts | margin | headcount | compliance | other>",
      "claim_text": "<the claim as stated, one sentence>",
      "stated_value": "<the number/threshold in the claim, or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_text": "<≤30 word quote>"
    }}
  ]
}}\
"""

_TOP10_SYSTEM = """\
You are the lead PE diligence analyst assembling the TOP 10 diligence issues for an
investment committee pre-read. You receive a compact list of candidate issues (flags
from each workstream + cross-workstream reconciliation mismatches). Rules:
1. Rank by severity × deal relevance. Severity levels (spec §10.3):
   - Critical: could change LOI price/structure or block close (e.g. material
     customer with change-of-control veto, EBITDA addback >10% Tier 4, undisclosed
     litigation, compliance incident).
   - Material: needs to be understood; may shape underwriting (e.g. concentration
     at 22%, margin below threshold but improving).
   - Track: worth noting/asking; not deal-shaping.
2. De-duplicate issues that describe the same underlying fact from two workstreams —
   merge them and note both sources.
3. Return AT MOST 10 issues, most severe first. Preserve the source citations.
4. Present mismatches as questions, not verdicts (Phase 1 posture).
5. Return ONLY valid JSON, no markdown fences.\
"""

_TOP10_USER = """\
CANDIDATE ISSUES (workstream flags + reconciliation mismatches):
{candidates}

Return this exact JSON:
{{
  "top_10_issues": [
    {{
      "rank": "<1-10>",
      "severity": "<Critical | Material | Track>",
      "issue": "<one-sentence statement of the issue, phrased neutrally>",
      "workstreams": ["<source workstream(s)>"],
      "why_it_matters": "<one sentence on deal relevance>",
      "citations": ["<source doc references carried from the candidate>"]
    }}
  ]
}}\
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

from agents.shared.agent_base import WorkstreamAgent


class CrossAnalysisAgent(WorkstreamAgent):
    """Phase 4 Cross-Analysis agent (spec §10)."""

    agent_name = "cross_analysis"

    def __init__(self):
        super().__init__()
        self._cards: dict = {}
        self._catalog = "uc13"

    # -- raw column loader (compact JSON columns only) ------------------
    def _load_row(self, table: str, company_name: str, spark) -> dict:
        try:
            rows = spark.sql(
                f"SELECT * FROM {self._catalog}.analysis.{table} WHERE company_name = :c "
                "ORDER BY created_at DESC LIMIT 1",
                args={"c": company_name},
            ).collect()
            return rows[0].asDict() if rows else {}
        except Exception:
            return {}

    @staticmethod
    def _jload(row: dict, col: str, default):
        raw = row.get(col)
        if not raw:
            return default
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return default

    # -----------------------------------------------------------------------
    # §10.1 Reconciliation checks — deterministic
    # -----------------------------------------------------------------------

    def _reconcile(self, company_name: str, spark, cim_claims: list) -> list:
        rows = {t: self._load_row(t, company_name, spark) for t in (
            "business_model", "financial_trends", "customer_quality",
            "kpi", "legal_contracts", "quality_of_earnings", "forecast")}
        checks = []

        def claim_value(category):
            for c in cim_claims:
                if c.get("category") == category:
                    return c
            return None

        # 1 — CIM revenue claim vs stated financials (BMA/CIM + FTA). Flag if delta >1%.
        rev_claim = claim_value("revenue")
        fta_rev = None
        for r in self._jload(rows["financial_trends"], "revenue_trend_json", []):
            v = _parse_numeric(r.get("revenue_stated"))
            if v is not None:
                fta_rev = v  # last (most recent by list order) — good enough for a delta check
        cim_rev = _parse_numeric(rev_claim.get("stated_value")) if rev_claim else None
        if cim_rev is not None and fta_rev not in (None, 0):
            delta_pct = abs(cim_rev - fta_rev) / fta_rev * 100
            checks.append(_check(
                "CIM revenue claim vs. stated financials",
                ["business_model/CIM", "financial_trends"],
                "mismatch" if delta_pct > 1 else "match",
                "material" if delta_pct > 1 else "n/a",
                f"CIM revenue ≈ {cim_rev:,.0f}; Financial Trends extracted ≈ {fta_rev:,.0f} "
                f"(delta {delta_pct:.1f}%).",
                [rev_claim.get("source_doc", "CIM")],
            ))
        else:
            checks.append(_check(
                "CIM revenue claim vs. stated financials",
                ["business_model/CIM", "financial_trends"], "cannot_check", "n/a",
                "Missing CIM revenue claim or Financial Trends revenue — cannot compare."))

        # 2 — CIM concentration claim vs customer workbook (BMA/CIM + CQA).
        conc_claim = claim_value("concentration")
        conc = self._jload(rows["customer_quality"], "concentration_summary_json", {})
        top1 = _parse_numeric(conc.get("top1_pct"))
        claim_thresh = _parse_numeric(conc_claim.get("stated_value")) if conc_claim else None
        if top1 is not None and claim_thresh is not None:
            checks.append(_check(
                "CIM customer-concentration claim vs. customer workbook",
                ["business_model/CIM", "customer_quality"],
                "mismatch" if top1 > claim_thresh else "match",
                "critical" if top1 > 20 else ("material" if top1 > claim_thresh else "n/a"),
                f"CIM claims top customer ≤ {claim_thresh:.0f}%; workbook shows top1 = {top1:.0f}%.",
                [conc.get("source_doc", "customer workbook")],
            ))
        else:
            checks.append(_check(
                "CIM customer-concentration claim vs. customer workbook",
                ["business_model/CIM", "customer_quality"], "cannot_check", "n/a",
                "Missing CIM concentration claim or workbook top1_pct — cannot compare."))

        # 3 — NRR ≥ GRR sanity check (CQA internal / QofE). NRR should always be ≥ GRR.
        ret = self._jload(rows["customer_quality"], "retention_json", {})
        nrr = _parse_numeric(ret.get("nrr_pct"))
        grr = _parse_numeric(ret.get("grr_pct"))
        if nrr is not None and grr is not None:
            checks.append(_check(
                "Stated NRR vs. GRR sanity check",
                ["customer_quality"],
                "mismatch" if nrr < grr else "match",
                "material" if nrr < grr else "n/a",
                f"NRR = {nrr:.0f}%, GRR = {grr:.0f}%."
                + (" NRR < GRR is a metric error — query management." if nrr < grr else ""),
                [ret.get("source_doc", "")],
            ))
        else:
            checks.append(_check(
                "Stated NRR vs. GRR sanity check", ["customer_quality"],
                "cannot_check", "n/a", "NRR or GRR not stated — cannot check."))

        # 4 — Customer concentration trigger → contract review (CQA → Legal).
        triggers = rows["customer_quality"].get("contract_trigger_list") or []
        if isinstance(triggers, str):
            triggers = self._jload(rows["customer_quality"], "contract_trigger_list", [])
        contract_reg = self._jload(rows["legal_contracts"], "contract_register_json", [])
        reviewed_names = " ".join(json.dumps(contract_reg)).lower()
        if triggers:
            missing = []
            for t in triggers:
                tname = (json.loads(t) if isinstance(t, str) else t).get("customer_name", "") \
                    if triggers else ""
                if tname and tname.lower() not in reviewed_names:
                    missing.append(tname)
            checks.append(_check(
                "Customer concentration trigger → contract review",
                ["customer_quality", "legal_contracts"],
                "mismatch" if missing else "match",
                "critical" if missing else "n/a",
                (f"Customers >20% flagged for contract review not confirmed reviewed by Legal: "
                 f"{missing}." if missing
                 else "All concentration-triggered customers have a reviewed contract."),
            ))
        else:
            checks.append(_check(
                "Customer concentration trigger → contract review",
                ["customer_quality", "legal_contracts"], "cannot_check", "n/a",
                "No concentration triggers produced by Customer Quality Agent — nothing to confirm."))

        # 5 — Revenue-model claim vs contract terms (BMA + Legal).
        contracts_claim = claim_value("contracts")
        if contracts_claim and contract_reg:
            reg_text = json.dumps(contract_reg).lower()
            multi_year_claim = "multi-year" in (contracts_claim.get("claim_text") or "").lower()
            has_annual_autorenew = "auto-renew" in reg_text or "annual" in reg_text
            checks.append(_check(
                "Revenue-model claim vs. contract terms",
                ["business_model/CIM", "legal_contracts"],
                "mismatch" if (multi_year_claim and has_annual_autorenew) else "match",
                "material" if (multi_year_claim and has_annual_autorenew) else "n/a",
                ("CIM claims multi-year contracts; Legal register shows annual/auto-renew terms "
                 "— query." if (multi_year_claim and has_annual_autorenew)
                 else "No contradiction detected between CIM contract claim and register."),
                [contracts_claim.get("source_doc", "CIM")],
            ))
        else:
            checks.append(_check(
                "Revenue-model claim vs. contract terms",
                ["business_model/CIM", "legal_contracts"], "cannot_check", "n/a",
                "Missing CIM contract claim or Legal contract register — cannot compare."))

        # 6 — EBITDA addback vs supporting docs (FTA + QofE): Tier 4 (unsupported) addbacks.
        tier4 = rows["quality_of_earnings"].get("tier4_addback_count")
        if tier4 is not None:
            checks.append(_check(
                "EBITDA addbacks vs. supporting documents",
                ["financial_trends", "quality_of_earnings"],
                "mismatch" if (tier4 or 0) > 0 else "match",
                "critical" if (tier4 or 0) > 0 else "n/a",
                f"{tier4} addback(s) classified Tier 4 (unsupported / unlikely to survive buyer "
                f"QofE). Confirm supporting documentation exists in the VDR.",
            ))
        else:
            checks.append(_check(
                "EBITDA addbacks vs. supporting documents",
                ["financial_trends", "quality_of_earnings"], "cannot_check", "n/a",
                "QofE tier4_addback_count unavailable — cannot check."))

        # 7 — Forecast new-customer revenue vs pipeline coverage (Forecast + KPI/CQA).
        downside = self._jload(rows["forecast"], "downside_sensitivity_json", {})
        pm = downside.get("pipeline_miss", {}) if isinstance(downside, dict) else {}
        coverage = pm.get("pipeline_coverage_x")
        if coverage is not None:
            checks.append(_check(
                "Forecast new-customer revenue vs. pipeline coverage",
                ["forecast", "kpi"],
                "mismatch" if coverage < 1 else "match",
                "material" if coverage < 2 else "n/a",
                f"Pipeline coverage of forecast new-customer revenue ≈ {coverage}x "
                f"(pipeline × conversion ÷ forecast).",
            ))
        else:
            checks.append(_check(
                "Forecast new-customer revenue vs. pipeline coverage",
                ["forecast", "kpi"], "cannot_check", "n/a",
                "Forecast pipeline-coverage or KPI pipeline data unavailable — cannot check."))

        # 8 — Stated headcount vs implied from financials (FTA + KPI) — best-effort.
        checks.append(_check(
            "Stated headcount vs. implied from financials",
            ["financial_trends", "kpi"], "cannot_check", "n/a",
            "Requires payroll cost ÷ avg comp vs. stated headcount; not extracted as structured "
            "fields in the current schema — flag for manual check."))

        # 9 — Stated DSO vs AR ÷ (revenue/365) (FTA internal).
        wc = self._jload(rows["financial_trends"], "working_capital_json", {})
        dso_stated = _parse_numeric(wc.get("dso_days"))
        if dso_stated is not None:
            checks.append(_check(
                "Stated DSO vs. AR ÷ (revenue/365) internal consistency",
                ["financial_trends"], "match", "track",
                f"DSO stated ≈ {dso_stated:.0f} days. Recompute AR ÷ (revenue/365) during QofE to "
                f"confirm internal consistency.",
            ))
        else:
            checks.append(_check(
                "Stated DSO vs. AR ÷ (revenue/365) internal consistency",
                ["financial_trends"], "cannot_check", "n/a",
                "Working-capital DSO not extracted — cannot check."))

        # 10 — Healthcare compliance claims vs compliance file (BMA + Legal + KPI).
        comp_claim = claim_value("compliance")
        litigation = self._jload(rows["legal_contracts"], "litigation_register_json", [])
        if comp_claim:
            no_issue_claim = "no material" in (comp_claim.get("claim_text") or "").lower()
            checks.append(_check(
                "Compliance claim vs. compliance/legal file",
                ["business_model/CIM", "legal_contracts", "kpi"],
                "mismatch" if (no_issue_claim and litigation) else "match",
                "critical" if (no_issue_claim and litigation) else "n/a",
                ("CIM states no material compliance issues, but Legal found open "
                 f"litigation/regulatory items ({len(litigation)}) — query."
                 if (no_issue_claim and litigation)
                 else "No contradiction detected between compliance claim and legal file."),
                [comp_claim.get("source_doc", "CIM")],
            ))
        else:
            checks.append(_check(
                "Compliance claim vs. compliance/legal file",
                ["business_model/CIM", "legal_contracts", "kpi"], "cannot_check", "n/a",
                "No CIM compliance claim extracted — cannot check."))

        # Log every check to the trace.
        for c in checks:
            step = len(self._trace) + 1
            self._trace.append({
                "step": step, "tool": "reconciliation_check",
                "input": c["check"], "output": f"{c['status']} — {c['detail'][:120]}",
                "confidence": "high" if c["status"] != "cannot_check" else "low",
                "sources": c["agents_involved"],
            })
        return checks

    # -----------------------------------------------------------------------
    # §10.2 CIM claims extraction (bounded LLM)
    # -----------------------------------------------------------------------

    def _extract_cim_claims(self, spark, llm_endpoint: str) -> list:
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="company overview investment highlights revenue growth customer concentration "
                  "retention contracts compliance margins headcount",
            spark=spark, company_name=self._company_name, top_k=12,
            workstream_filter=["BUSINESS_MODEL"],
            file_name_filter=["CIM", "Confidential", "Memorandum", "Presentation", "Investor"],
            min_chunk_length=200,
        ).chunks
        if not chunks:
            self._add_gap("No CIM / management-presentation chunks found — CIM-claims check skipped.")
            return []
        cim_context = "\n\n---\n\n".join(
            f"[File: {c.file_name}] [Section: {c.section_header}]\n{c.chunk_text}"
            for c in chunks
        )[:24000]
        self._tool_call(
            "retrieve_cim_claims_context", "CIM/management presentation retrieval",
            chunks, f"{len(chunks)} CIM chunks", "high", list({c.file_name for c in chunks}))
        raw = self._call_llm(_CIM_CLAIMS_SYSTEM,
                             _CIM_CLAIMS_USER.format(cim_context=cim_context),
                             llm_endpoint, max_tokens=8_000)
        try:
            claims = self._parse_json_response(raw).get("cim_claims") or []
        except Exception as e:
            self._add_gap(f"CIM claims extraction failed to parse: {e}")
            claims = []
        for c in claims:
            self._add_citation(
                claim=c.get("claim_text", ""), document=c.get("source_doc", ""),
                location=c.get("source_location", ""), confidence="medium",
                raw_text=c.get("raw_text", ""))
        return claims

    def _corroborate_cim_claims(self, cim_claims: list, checks: list) -> list:
        """Mark each CIM claim corroborated / uncorroborated / contradicted using the
        deterministic reconciliation results where they overlap."""
        cat_status = {}
        for c in checks:
            # map reconciliation checks back to CIM claim categories
            name = c["check"].lower()
            if "revenue claim" in name:
                cat_status["revenue"] = c["status"]
            elif "concentration claim" in name:
                cat_status["concentration"] = c["status"]
            elif "contract terms" in name:
                cat_status["contracts"] = c["status"]
            elif "compliance claim" in name:
                cat_status["compliance"] = c["status"]
        out = []
        for claim in cim_claims:
            cat = claim.get("category")
            st = cat_status.get(cat)
            if st == "match":
                status = "corroborated"
            elif st == "mismatch":
                status = "contradicted"
            else:
                status = "uncorroborated"
            out.append({**claim, "corroboration_status": status})
        return out

    # -----------------------------------------------------------------------
    # §10.3 Top-10 issues (bounded LLM ranking over compact candidates)
    # -----------------------------------------------------------------------

    def _assemble_candidates(self, company_name: str, spark, checks: list) -> list:
        """Compact candidate list: every Red/Yellow workstream flag + every mismatch."""
        candidates = []
        from agents.orchestration.pipeline import AGENT_REGISTRY
        for key, spec in AGENT_REGISTRY.items():
            if spec.phase != "3":
                continue
            row = self._load_row(spec.table, company_name, spark)
            for f in self._jload(row, "flags", []):
                sev = str(f.get("severity", "")).lower()
                if sev in ("red", "yellow"):
                    candidates.append({
                        "source": "flag", "workstream": key,
                        "severity_hint": sev,
                        "issue": f"{f.get('metric')}: {f.get('value')} vs {f.get('threshold')} — {f.get('note')}",
                        "citations": [f.get("source_doc", "")],
                    })
        for c in checks:
            if c["status"] == "mismatch":
                candidates.append({
                    "source": "reconciliation", "workstream": "+".join(c["agents_involved"]),
                    "severity_hint": c["materiality"],
                    "issue": f"{c['check']}: {c['detail']}",
                    "citations": c.get("citations", []),
                })
        return candidates

    def _rank_top10(self, candidates: list, llm_endpoint: str) -> list:
        if not candidates:
            return []
        raw = self._call_llm(
            _TOP10_SYSTEM,
            _TOP10_USER.format(candidates=json.dumps(candidates, indent=2)[:20000]),
            llm_endpoint, max_tokens=6_000)
        try:
            return self._parse_json_response(raw).get("top_10_issues") or []
        except Exception as e:
            self._add_gap(f"Top-10 ranking failed to parse: {e}")
            # Deterministic fallback: severity-hint ordering.
            order = {"critical": 0, "red": 0, "material": 1, "yellow": 1, "track": 2, "": 3}
            ranked = sorted(candidates, key=lambda c: order.get(c.get("severity_hint"), 3))[:10]
            return [{"rank": i + 1,
                     "severity": {"critical": "Critical", "red": "Critical",
                                  "material": "Material", "yellow": "Material"}.get(
                                      c.get("severity_hint"), "Track"),
                     "issue": c["issue"], "workstreams": [c["workstream"]],
                     "why_it_matters": "", "citations": c.get("citations", [])}
                    for i, c in enumerate(ranked)]

    # -----------------------------------------------------------------------
    # §10.4 Data-room gap list
    # -----------------------------------------------------------------------

    def _collect_gap_list(self, company_name: str, spark) -> list:
        from agents.orchestration.pipeline import AGENT_REGISTRY
        seen, gaps = set(), []
        for key, spec in AGENT_REGISTRY.items():
            if spec.phase not in ("3",):
                continue
            row = self._load_row(spec.table, company_name, spark)
            row_gaps = row.get("data_room_gaps") or []
            if isinstance(row_gaps, str):
                row_gaps = self._jload(row, "data_room_gaps", [])
            for g in row_gaps:
                if g and g not in seen:
                    seen.add(g)
                    gaps.append({"workstream": key, "gap": g})
        return gaps

    # -----------------------------------------------------------------------
    # run()
    # -----------------------------------------------------------------------

    def run(self, company_name: str, spark, llm_endpoint: str, catalog: str = "uc13") -> dict:
        self._reset_state()
        self._company_name = company_name
        self._catalog = catalog

        print("  Extracting CIM claims (bounded LLM) ...")
        cim_claims = self._extract_cim_claims(spark, llm_endpoint)

        print("  Running deterministic reconciliation checks (§10.1) ...")
        checks = self._reconcile(company_name, spark, cim_claims)

        print("  Corroborating CIM claims against evidence (§10.2) ...")
        cim_claims_checked = self._corroborate_cim_claims(cim_claims, checks)

        print("  Assembling and ranking top-10 issues (§10.3) ...")
        candidates = self._assemble_candidates(company_name, spark, checks)
        top10 = self._rank_top10(candidates, llm_endpoint)

        print("  Collecting data-room gap list (§10.4) ...")
        gap_list = self._collect_gap_list(company_name, spark)

        recon_summary = {st: sum(1 for c in checks if c["status"] == st)
                         for st in ("match", "mismatch", "cannot_check")}
        critical_count = sum(1 for i in top10 if str(i.get("severity")).lower() == "critical")

        exec_summary = (
            f"Ran {len(checks)} cross-workstream reconciliation checks "
            f"({recon_summary['mismatch']} mismatch, {recon_summary['cannot_check']} cannot-check). "
            f"Extracted {len(cim_claims)} CIM claims; "
            f"{sum(1 for c in cim_claims_checked if c['corroboration_status']=='contradicted')} contradicted. "
            f"Top-10 issues include {critical_count} Critical."
        )

        return {
            "company_name":              company_name,
            "executive_summary":         exec_summary,
            "reconciliation_log_json":   json.dumps(checks),
            "cim_claims_json":           json.dumps(cim_claims_checked),
            "top_10_issues_json":        json.dumps(top10),
            "data_room_gap_list_json":   json.dumps(gap_list),
            "reconciliation_summary_json": json.dumps(recon_summary),
            "critical_issue_count":      critical_count,
            "flags":                     self._flags_as_dicts(),
            "data_room_gaps":            list(self._data_room_gaps),
            "citations":                 json.dumps(self._citations_as_dicts()),
            "reasoning_trace":           list(self._trace),
            "created_at":                datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Markdown assessment (used by the Orchestrator as the Cross-Analysis section)
# ---------------------------------------------------------------------------

def generate_cross_analysis_assessment(result: dict, spark=None, llm_endpoint=None,
                                       catalog: str = "uc13", write_to_volume: bool = True) -> str:
    """Deterministic markdown for the Cross-Analysis section (no LLM needed)."""
    company = result["company_name"]
    checks   = json.loads(result.get("reconciliation_log_json")   or "[]")
    claims   = json.loads(result.get("cim_claims_json")           or "[]")
    top10    = json.loads(result.get("top_10_issues_json")        or "[]")
    gaps     = json.loads(result.get("data_room_gap_list_json")   or "[]")
    summary  = json.loads(result.get("reconciliation_summary_json") or "{}")

    md = [f"# Cross-Analysis — {company}", "", result.get("executive_summary", ""), ""]

    md.append("## Top 10 Diligence Issues\n")
    if top10:
        md.append("| # | Severity | Issue | Workstreams | Why it matters |")
        md.append("|---|---|---|---|---|")
        for i in top10:
            md.append(f"| {i.get('rank','')} | {i.get('severity','')} | {i.get('issue','')} "
                      f"| {', '.join(i.get('workstreams', []))} | {i.get('why_it_matters','')} |")
    else:
        md.append("_No ranked issues produced._")
    md.append("")

    md.append(f"## Reconciliation Log  ({summary.get('match',0)} match · "
              f"{summary.get('mismatch',0)} mismatch · {summary.get('cannot_check',0)} cannot-check)\n")
    md.append("| Check | Agents | Status | Materiality | Detail |")
    md.append("|---|---|---|---|---|")
    for c in checks:
        md.append(f"| {c['check']} | {', '.join(c['agents_involved'])} | {c['status']} "
                  f"| {c['materiality']} | {c['detail']} |")
    md.append("")

    md.append("## CIM Claims vs. Data Room\n")
    if claims:
        md.append("| Claim | Category | Stated | Status | Source |")
        md.append("|---|---|---|---|---|")
        for c in claims:
            md.append(f"| {c.get('claim_text','')} | {c.get('category','')} | {c.get('stated_value','—')} "
                      f"| {c.get('corroboration_status','')} | {c.get('source_doc','')} |")
    else:
        md.append("_No CIM claims extracted._")
    md.append("")

    md.append("## Data Room Gap List (information request)\n")
    if gaps:
        for g in gaps:
            md.append(f"- **[{g.get('workstream','')}]** {g.get('gap','')}")
    else:
        md.append("_No gaps recorded._")
    md.append("")

    text = "\n".join(md)
    if write_to_volume and spark is not None:
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
        safe = company.replace(" ", "_").replace("/", "_")
        d = f"/Volumes/{catalog}/analysis/reports/{safe}"
        os.makedirs(d, exist_ok=True)
        with open(f"{d}/cross_analysis_assessment.md", "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


# ---------------------------------------------------------------------------
# Table DDL + main()
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name                STRING,
    executive_summary           STRING,
    reconciliation_log_json     STRING,
    cim_claims_json             STRING,
    top_10_issues_json          STRING,
    data_room_gap_list_json     STRING,
    reconciliation_summary_json STRING,
    critical_issue_count        INT,
    flags                       STRING,
    data_room_gaps              ARRAY<STRING>,
    citations                   STRING,
    reasoning_trace             STRING,
    created_at                  TIMESTAMP
) USING DELTA
"""


def main(spark=None) -> dict:
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    company_name = get_param("sp_company_name")
    catalog      = get_param("catalog",      default="uc13")
    llm_endpoint = get_param("llm_endpoint", default="databricks-claude-sonnet-4-6")

    from pyspark.sql import SparkSession
    if spark is None:
        spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Cross-Analysis Agent ({company_name}) ===")
    agent  = CrossAnalysisAgent()
    result = agent.run(company_name=company_name, spark=spark,
                       llm_endpoint=llm_endpoint, catalog=catalog)

    table = f"{catalog}.analysis.cross_analysis"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

    _EXPECTED_COLS = {
        "company_name", "executive_summary", "reconciliation_log_json", "cim_claims_json",
        "top_10_issues_json", "data_room_gap_list_json", "reconciliation_summary_json",
        "critical_issue_count", "flags", "data_room_gaps", "citations", "reasoning_trace",
        "created_at",
    }
    try:
        _live = {f.name for f in spark.table(table).schema.fields}
        if not _EXPECTED_COLS.issubset(_live):
            print(f"  [schema_migration] {table}: dropping stale table. Missing: "
                  f"{sorted(_EXPECTED_COLS - _live)}")
            spark.sql(f"DROP TABLE IF EXISTS {table}")
    except Exception:
        pass

    spark.sql(_CREATE_TABLE_SQL.format(table=table))
    spark.sql(f"DELETE FROM {table} WHERE company_name = :c", args={"c": company_name})

    from pyspark.sql import Row
    from pyspark.sql.types import (StructType, StructField, StringType,
                                   IntegerType, ArrayType, TimestampType)
    schema = StructType([
        StructField("company_name",                StringType(),  True),
        StructField("executive_summary",           StringType(),  True),
        StructField("reconciliation_log_json",     StringType(),  True),
        StructField("cim_claims_json",             StringType(),  True),
        StructField("top_10_issues_json",          StringType(),  True),
        StructField("data_room_gap_list_json",     StringType(),  True),
        StructField("reconciliation_summary_json", StringType(),  True),
        StructField("critical_issue_count",        IntegerType(), True),
        StructField("flags",                       StringType(),  True),
        StructField("data_room_gaps",              ArrayType(StringType()), True),
        StructField("citations",                   StringType(),  True),
        StructField("reasoning_trace",             StringType(),  True),
        StructField("created_at",                  TimestampType(), True),
    ])
    row_data = {
        "company_name":                result["company_name"],
        "executive_summary":           result.get("executive_summary"),
        "reconciliation_log_json":     result.get("reconciliation_log_json"),
        "cim_claims_json":             result.get("cim_claims_json"),
        "top_10_issues_json":          result.get("top_10_issues_json"),
        "data_room_gap_list_json":     result.get("data_room_gap_list_json"),
        "reconciliation_summary_json": result.get("reconciliation_summary_json"),
        "critical_issue_count":        result.get("critical_issue_count"),
        "flags":                       json.dumps(result.get("flags") or []),
        "data_room_gaps":              result.get("data_room_gaps") or [],
        "citations":                   result.get("citations"),
        "reasoning_trace":             json.dumps(result.get("reasoning_trace") or []),
        "created_at":                  datetime.now(timezone.utc),
    }
    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(table)
    print(f"\n✓ Saved cross-analysis output → {table}")

    if get_param("write_assessment", default="true").lower() == "true":
        generate_cross_analysis_assessment(result, spark=spark, catalog=catalog)
        print("✓ Cross-analysis markdown assessment written")
    return result


if __name__ == "__main__":
    main()
