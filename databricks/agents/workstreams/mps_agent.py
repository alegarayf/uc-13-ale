"""mps_agent.py — MPS (Minimum Pursuit Score) agent.

docs/plans/mps_score/mps_score_1st_draft.md §4, §6.1, §7. One bounded LLM
call scoring the 7 MPS categories independently, using the rubric YAML
(``mps_rubric.py``) for both the prompt content and the pure post-call
scoring arithmetic. Never raises: any failure (missing/invalid rubric, LLM
timeout, malformed JSON, out-of-range score) degrades to
``mps_status="degraded"`` so the executive review can still render.

T5 scope (docs/plans/mps_score/tasks/T5_retrieval_persistencia.md): the real
§7.4/§A.3b Growth mindset retrieval gating on ``cim_detected``, and the
agent's own append-only Delta write to ``{catalog}.analysis.mps_score``
(§9).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from agents.exec_summary.mps_rubric import RubricError, load_rubric, mps_total, mps_verdict
from agents.exec_summary.rainmaker_narrative import _NON_FABRICATION_RULE, _base_digest
from agents.exec_summary.rainmaker_view import _cim_presence, _financial_table
from agents.shared.agent_base import WorkstreamAgent
from agents.subagents.workstream.financial.context_utils import semantic_search_with_fallback

_MPS_MAX_TOKENS = 4_000  # ~120s serving timeout ceiling — databricks/CLAUDE.md

# The six keys the LLM is allowed to return per category (§4.1) are "key",
# "score", "rationale", "counter_evidence", "sub_axis_notes", "confidence".
# Everything else in the agent's output contract (display_name,
# evidence_basis, evidence_refs, rubric_version, threshold, run_mode,
# generated_at, total, verdict, mps_status, degraded_reason) is stamped by
# this module after the call, never asked of the model.
_CONFIDENCE_LEVELS = ("high", "medium", "low")


# ---------------------------------------------------------------------------
# §7.3 — MPS digest: the shared whitelisted core plus the four MPS-only
# additions. Composes from _base_digest() rather than copy-pasting it, so
# the whitelist discipline that module's docstring guarantees survives here
# too (tests/test_rainmaker_narrative.py guards the shared core).
# ---------------------------------------------------------------------------


def _ma_history(company_framing: dict[str, Any]) -> list[str]:
    events: list[str] = []
    for change in company_framing.get("recent_changes") or []:
        if not isinstance(change, dict):
            continue
        if str(change.get("change_type") or "").lower() != "ma":
            continue
        description = str(change.get("description") or "").strip()
        if description:
            events.append(description)
    return events


_LEGAL_STRUCTURAL_RISK_MARKERS = ("coc", "regulatory", "litigation", "legal_matter")


def _legal_digest(bundle: dict[str, Any]) -> dict[str, Any]:
    legal = bundle.get("legal") or {}
    structural_flags: list[str] = []
    for flag in legal.get("top_flags") or []:
        if not isinstance(flag, dict):
            continue
        metric = str(flag.get("metric") or "").lower()
        if not any(marker in metric for marker in _LEGAL_STRUCTURAL_RISK_MARKERS):
            continue
        note = str(flag.get("note") or flag.get("value") or "").strip()
        if note:
            structural_flags.append(note)
    return {
        "section_confidence": str(legal.get("section_confidence") or ""),
        "coc_regulatory_litigation_flags": structural_flags[:5],
        "top_gaps": [str(g) for g in (legal.get("top_gaps") or []) if str(g).strip()][:5],
    }


def _qoe_digest(bundle: dict[str, Any]) -> dict[str, Any]:
    qoe = bundle.get("qoe") or {}
    addback_quality_flags: list[str] = []
    for flag in qoe.get("flags") or []:
        if not isinstance(flag, dict):
            continue
        note = str(flag.get("note") or flag.get("value") or "").strip()
        if note:
            addback_quality_flags.append(note)
    return {
        "addback_pct_of_ebitda": str(qoe.get("addback_pct_of_ebitda") or ""),
        "tier_summary": str(qoe.get("tier_summary") or ""),
        "addback_quality_flags": addback_quality_flags[:5],
    }


def _build_mps_digest(bundle: dict[str, Any], growth_mindset_evidence: str = "") -> dict[str, Any]:
    """Everything ``_base_digest`` assembles, plus the four §7.3 additions:
    workforce/M&A history, the full financial series, confidence_by_area,
    and the legal/QoE structural-risk summaries — plus §7.4/§A.3b's
    ``growth_mindset_evidence`` (the one conditional retrieval call's
    result, or an explicit not-attempted/no-signal note)."""
    digest = _base_digest(bundle, _financial_table(bundle))
    company_framing = bundle.get("company_framing") or {}
    digest["workforce_notes"] = str(company_framing.get("workforce_notes") or "")
    digest["ma_history"] = _ma_history(company_framing)
    digest["financials_full_series"] = (bundle.get("financials") or {}).get("table_rows") or []
    digest["confidence_by_area"] = dict(bundle.get("confidence_by_area") or {})
    digest["legal"] = _legal_digest(bundle)
    digest["qoe"] = _qoe_digest(bundle)
    digest["growth_mindset_evidence"] = growth_mindset_evidence
    return digest


# ---------------------------------------------------------------------------
# §7.4/§A.3b — Growth mindset retrieval: the one bounded, path-aware
# exception. Never more than one call, never for any other category
# (§A.8 evaluated and rejected extending this to Financeable/
# Transformational equity).
# ---------------------------------------------------------------------------

_GROWTH_MINDSET_NOT_ATTEMPTED_CIM = (
    "not attempted — CIM-scoped mode; score growth_mindset from proxies visible in the digest "
    "only."
)
_GROWTH_MINDSET_NOT_ATTEMPTED_NO_SPARK = (
    "not attempted — no Spark session available; score growth_mindset from proxies visible in "
    "the digest only."
)
_GROWTH_MINDSET_NO_SIGNAL = (
    "full-room search attempted — found no additional signal beyond the digest."
)

_GROWTH_MINDSET_RETRIEVAL_QUERY = (
    "leadership tenure prior M&A execution senior hires organizational chart repeatable systems "
    "process professionalization founder growth strategy management team background executive "
    "appointments"
)

_GROWTH_MINDSET_CAP_PER_CHUNK = 800
_GROWTH_MINDSET_TOTAL_BUDGET = 6_000


def _cim_detected(bundle: dict[str, Any]) -> bool:
    """§7.4's gating signal — the same ``cim_detected=`` marker
    ``rainmaker_view._cim_presence()`` reads from
    ``meta.basis_of_preparation``."""
    return _cim_presence(bundle) == "PRESENT"


def _growth_mindset_evidence(company_name: str, spark: Any, cim_detected: bool) -> tuple[str, bool]:
    """Returns ``(evidence_text, retrieval_used)``.

    Skips entirely when ``cim_detected=True`` (§A.3b — re-searching the same
    single CIM file BMA/FTA already mined has near-zero marginal value).
    When ``cim_detected=False``, runs exactly one
    ``semantic_search_with_fallback`` call, filtered by ``company_name``
    (same isolation pattern every other agent uses). Never raises: a failed
    or empty/unusable search degrades to an explicit no-signal note, never
    a guess.
    """
    if cim_detected:
        return _GROWTH_MINDSET_NOT_ATTEMPTED_CIM, False
    if spark is None:
        return _GROWTH_MINDSET_NOT_ATTEMPTED_NO_SPARK, False

    try:
        result, _used_fallback = semantic_search_with_fallback(
            company_name=company_name,
            spark=spark,
            query=_GROWTH_MINDSET_RETRIEVAL_QUERY,
            workstream_filter=["BUSINESS_MODEL"],
            top_k=6,
            file_name_filter=None,
            min_chunk_length=150,
            min_results=3,
            intent_id="mps.growth_mindset.q1_leadership_and_ma_proxies",
        )
        chunks = list(result.chunks or [])
    except Exception as exc:  # noqa: BLE001 - retrieval must never raise (§7.4 non-negotiable)
        print(f"[mps_agent] growth mindset retrieval failed, scoring from proxies: {exc!r}")
        chunks = []

    if not chunks:
        return _GROWTH_MINDSET_NO_SIGNAL, True

    parts: list[str] = []
    used = 0
    for chunk in chunks:
        text = (getattr(chunk, "chunk_text", "") or "").strip()
        if not text:
            continue
        block = f"[File: {getattr(chunk, 'file_name', '')}] {text[:_GROWTH_MINDSET_CAP_PER_CHUNK]}"
        if used + len(block) > _GROWTH_MINDSET_TOTAL_BUDGET:
            break
        parts.append(block)
        used += len(block)

    evidence_text = "\n\n---\n\n".join(parts)
    return (evidence_text, True) if evidence_text else (_GROWTH_MINDSET_NO_SIGNAL, True)


# ---------------------------------------------------------------------------
# §7.2 — system prompt assembly, built at call time from the rubric file.
# R-E is load-bearing here: nothing below ever references rubric["threshold"]
# or the mps_total()/mps_verdict() formula.
# ---------------------------------------------------------------------------

_ROLE_FRAMING = (
    "You are scoring a company against Rallyday's Minimum Pursuit Score (MPS) rubric — "
    "Rallyday's own first-pass private-equity screening standard, used internally by its "
    "investment team to decide whether a deal is worth pursuing further. Score exactly the "
    "7 categories defined below, each one independently, on a 1-5 scale."
)

_EVIDENCE_BASIS_FRAMING = {
    "document_derived": (
        "Evidence basis: document_derived — this is scoreable from the data room. Apply the "
        "standard non-fabrication rule above; do not invent a document-derived fact."
    ),
    "contact_dependent": (
        "Evidence basis: contact_dependent — this genuinely requires management contact, which "
        "is not available. At this stage, score from the proxies described in the definition "
        "only. The rationale MUST carry an explicit proxy caveat (e.g. 'assessed from proxies "
        "only; no management contact available')."
    ),
    "judgment_over_context": (
        "Evidence basis: judgment_over_context — this is not a data-room fact lookup. Score it "
        "as a judgment call using the financial/operating profile plus Rallyday's own playbook "
        "below. Frame the rationale explicitly as a judgment, not as an extracted fact."
    ),
}


def _category_prompt_block(category: dict[str, Any], playbook_text: str) -> str:
    lines = [
        f'### {category["display_name"]} (key: "{category["key"]}")',
        category["definition"].strip(),
        _EVIDENCE_BASIS_FRAMING.get(category["evidence_basis"], ""),
    ]
    if category["evidence_basis"] == "judgment_over_context" and playbook_text:
        lines.append(f"Rallyday's playbook: {playbook_text}")
    lines.append(f'Anchor for score 5: {category["anchors"]["5"].strip()}')
    lines.append(f'Anchor for score 3: {category["anchors"]["3"].strip()}')
    lines.append(f'Anchor for score 1: {category["anchors"]["1"].strip()}')
    sub_axes = (category.get("required_commentary") or {}).get("sub_axes") or []
    if sub_axes:
        lines.append(
            "This category has named sub-axes — cover only the ones that materially apply to "
            "this business (never pad with one that does not apply), each as its own "
            "sub_axis_notes entry labeled with its axis name: " + ", ".join(sub_axes)
        )
    return "\n".join(lines)


def _assemble_system_prompt(rubric: dict[str, Any]) -> str:
    playbook_text = str((rubric.get("rallyday_playbook") or {}).get("text") or "").strip()
    category_blocks = "\n\n".join(
        _category_prompt_block(category, playbook_text) for category in rubric["categories"]
    )
    calibration_rules = "\n".join(
        f'{rule["key"]}: {rule["text"].strip()}' for rule in rubric.get("calibration_rules") or []
    )
    interpolation_rule = str(rubric.get("interpolation_rule") or "").strip()

    return f"""{_ROLE_FRAMING}

{_NON_FABRICATION_RULE}

CATEGORY DEFINITIONS, EVIDENCE BASIS AND ANCHORS (verbatim — never paraphrase or shorten a \
definition):

{category_blocks}

SCORE INTERPOLATION:
{interpolation_rule}

CALIBRATION RULES (apply to every category, without exception):
{calibration_rules}

GROWTH MINDSET EVIDENCE (§A.3b) — the user payload's "growth_mindset_evidence" field is the \
result of the one bounded, path-aware retrieval this pipeline runs for the growth_mindset \
category only, never for any other category:
- If it starts with "not attempted": score growth_mindset from the proxies already visible \
elsewhere in the digest, per the evidence-basis framing above.
- If it starts with "full-room search attempted — found no additional signal": still score from \
proxies, and the rationale for growth_mindset MUST read exactly "limited evidence — proxy-based; \
full-room search found no additional signal."
- Otherwise, it is retrieved data-room content bearing on leadership tenure, prior M&A execution, \
senior hires, or repeatable systems — use it as proxy evidence for growth_mindset, citing what it \
actually shows.

LENGTH DISCIPLINE (strict):
- "rationale": ONE sentence, at most ~180 characters.
- "counter_evidence": ONE sentence, at most ~180 characters — empty string "" if there is \
genuinely none.
- "sub_axis_notes": at most one short clause each, 1 to 4 entries — an empty list [] for every \
category except Manageable systemic risk.
- "confidence": one of "high", "medium", "low".

OUTPUT SHAPE — respond with ONLY a JSON object, no markdown fences. For EACH of the 7 categories \
return EXACTLY these six keys and nothing else — do not include display_name, evidence_basis, \
evidence_refs, total, or verdict; those are filled in separately, outside this call:
{{
  "categories": [
    {{"key": "<category key>", "score": <int 1-5>, "rationale": "<...>", "counter_evidence": \
"<...>", "sub_axis_notes": [{{"axis": "<axis>", "note": "<...>"}}], "confidence": \
"high|medium|low"}}
  ]
}}
Return all 7 categories, using each category's exact key from above."""


def _rationale_is_near_copy(rationale: str, definition: str) -> bool:
    """Cheap containment/overlap heuristic for the R-C failure mode (§A.7,
    plan §11 test 12) — a rationale that restates the category definition
    instead of citing a concrete fact. Diagnostic only: MPSAgent does not
    degrade on this, since R-C is enforced at generation time by the prompt
    above, not by post-call validation (§4.1 only validates key/score
    shape)."""
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    rationale_tokens = _tokens(rationale)
    definition_tokens = _tokens(definition)
    if not rationale_tokens or not definition_tokens:
        return False
    overlap = len(rationale_tokens & definition_tokens) / len(rationale_tokens)
    return overlap >= 0.6


# ---------------------------------------------------------------------------
# §4.1 — post-call validation and reordering. Never trust the model's
# ordering; reorder to rubric-file order; drop unknown keys; a key missing
# from the response scores None for that category without shifting the
# list; an out-of-range score or a structurally malformed response degrades
# the WHOLE result. Never silently repaired.
# ---------------------------------------------------------------------------


def _missing_category_row(category: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": category["key"],
        "display_name": category["display_name"],
        "score": None,
        "rationale": "",
        "counter_evidence": "",
        "sub_axis_notes": [],
        "evidence_basis": category["evidence_basis"],
        "evidence_refs": [],
        "confidence": "low",
    }


def _reorder_and_validate_categories(
    parsed: Any, rubric: dict[str, Any]
) -> tuple[list[dict[str, Any]] | None, bool]:
    if not isinstance(parsed, dict):
        return None, False
    raw_categories = parsed.get("categories")
    if not isinstance(raw_categories, list) or not raw_categories:
        return None, False

    by_key: dict[str, dict[str, Any]] = {}
    for entry in raw_categories:
        if not isinstance(entry, dict):
            return None, False
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            return None, False
        by_key[key] = entry  # unknown keys (not in rubric) are simply never looked up below

    result: list[dict[str, Any]] = []
    for category in rubric["categories"]:
        entry = by_key.get(category["key"])
        if entry is None:
            result.append(_missing_category_row(category))
            continue

        score = entry.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not (1 <= score <= 5):
            return None, False

        confidence = entry.get("confidence")
        if confidence not in _CONFIDENCE_LEVELS:
            confidence = "low"

        sub_axis_notes = []
        for note in entry.get("sub_axis_notes") or []:
            if isinstance(note, dict) and note.get("axis") and note.get("note"):
                sub_axis_notes.append({"axis": str(note["axis"]), "note": str(note["note"])})

        result.append(
            {
                "key": category["key"],
                "display_name": category["display_name"],
                "score": score,
                "rationale": str(entry.get("rationale") or ""),
                "counter_evidence": str(entry.get("counter_evidence") or ""),
                "sub_axis_notes": sub_axis_notes,
                "evidence_basis": category["evidence_basis"],
                "evidence_refs": [],
                "confidence": confidence,
            }
        )

    return result, True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _degraded_result(
    run_mode: str,
    rubric: dict[str, Any] | None,
    reason: str,
    cim_detected: bool = False,
    retrieval_used: bool = False,
) -> dict[str, Any]:
    rubric = rubric or {}
    return {
        "mps_status": "degraded",
        "rubric_version": rubric.get("rubric_version"),
        "threshold": rubric.get("threshold"),
        "run_mode": run_mode,
        "generated_at": _now_iso(),
        "categories": [],
        "total": None,
        "verdict": None,
        "degraded_reason": reason,
        "cim_detected": cim_detected,
        "retrieval_used": retrieval_used,
    }


# ---------------------------------------------------------------------------
# §9 — Delta persistence. Append-only: MPSAgent writes its own row, one per
# generation, to {catalog}.analysis.mps_score, following the same
# drop+recreate schema-drift guard as the sibling agents (kpi_agent.main(),
# legal_contracts_agent.py). _EXPECTED_COLS is the single source of truth
# for the migration (databricks/CLAUDE.md "Schema changes in analysis
# tables") — never add a separate migration cell. No CHECK constraint on
# run_mode: it is a plain STRING so §5.1's third mode can be persisted later
# without a migration. No DEFAULT clause is used, so no
# `delta.feature.allowColumnDefaults` TBLPROPERTIES opt-in is needed
# (databricks/CLAUDE.md "`DEFAULT` in a CREATE TABLE requires an explicit
# opt-in").
# ---------------------------------------------------------------------------

_EXPECTED_COLS = {
    "company_name",
    "catalog",
    "generated_at",
    "run_mode",
    "rubric_version",
    "total",
    "threshold",
    "verdict",
    "mps_status",
    "categories_json",
    "cim_detected",
    "retrieval_used",
    "llm_endpoint",
    "run_id",
}

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name     STRING,
    catalog          STRING,
    generated_at     TIMESTAMP,
    run_mode         STRING,
    rubric_version   STRING,
    total            DOUBLE,
    threshold        DOUBLE,
    verdict          STRING,
    mps_status       STRING,
    categories_json  STRING,
    cim_detected     BOOLEAN,
    retrieval_used   BOOLEAN,
    llm_endpoint     STRING,
    run_id           STRING
) USING DELTA
"""


def _mps_row(
    catalog: str, company_name: str, llm_endpoint: str, run_id: str, result: dict[str, Any]
) -> dict[str, Any]:
    generated_at = result.get("generated_at")
    try:
        generated_at_ts = datetime.fromisoformat(generated_at) if generated_at else _now_dt()
    except ValueError:
        generated_at_ts = _now_dt()
    return {
        "company_name": company_name,
        "catalog": catalog,
        "generated_at": generated_at_ts,
        "run_mode": result.get("run_mode"),
        "rubric_version": result.get("rubric_version"),
        "total": result.get("total"),
        "threshold": result.get("threshold"),
        "verdict": result.get("verdict"),
        "mps_status": result.get("mps_status"),
        "categories_json": json.dumps(result.get("categories") or []),
        "cim_detected": result.get("cim_detected"),
        "retrieval_used": result.get("retrieval_used"),
        "llm_endpoint": llm_endpoint,
        "run_id": run_id,
    }


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _write_mps_row(
    spark: Any, catalog: str, company_name: str, llm_endpoint: str, run_id: str, result: dict[str, Any]
) -> None:
    """Append-only Delta write (§9) — never overwrite/DELETE. Score history
    from day one is the point (§A.8): it is what makes a future multi-run
    trend view a rendering change over existing rows, not a data migration.
    """
    if spark is None:
        return

    table = f"{catalog}.analysis.mps_score"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

    try:
        _live_cols = {f.name for f in spark.table(table).schema.fields}
        if not _EXPECTED_COLS.issubset(_live_cols):
            _missing = _EXPECTED_COLS - _live_cols
            print(f"[mps_agent] {table}: dropping stale table. Missing cols: {sorted(_missing)}")
            spark.sql(f"DROP TABLE IF EXISTS {table}")
    except Exception:
        pass

    spark.sql(_CREATE_TABLE_SQL.format(table=table))

    from pyspark.sql import Row
    from pyspark.sql.types import (
        BooleanType,
        DoubleType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    schema = StructType(
        [
            StructField("company_name", StringType(), True),
            StructField("catalog", StringType(), True),
            StructField("generated_at", TimestampType(), True),
            StructField("run_mode", StringType(), True),
            StructField("rubric_version", StringType(), True),
            StructField("total", DoubleType(), True),
            StructField("threshold", DoubleType(), True),
            StructField("verdict", StringType(), True),
            StructField("mps_status", StringType(), True),
            StructField("categories_json", StringType(), True),
            StructField("cim_detected", BooleanType(), True),
            StructField("retrieval_used", BooleanType(), True),
            StructField("llm_endpoint", StringType(), True),
            StructField("run_id", StringType(), True),
        ]
    )

    row_data = _mps_row(catalog, company_name, llm_endpoint, run_id, result)
    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").saveAsTable(table)  # append-only (§9) — never overwrite


class MPSAgent(WorkstreamAgent):
    """MPS scoring agent (docs/plans/mps_score/mps_score_1st_draft.md §4.2).

    ``run()`` is deliberately NOT overridden: MPS is not a Phase-3 DAG agent
    and is never invoked via pipeline.py or mlflow ``predict``. The
    inherited ``NotImplementedError`` is correct — it fails loudly if
    someone wires MPS into the DAG by mistake.
    """

    agent_name = "mps"

    def score(
        self,
        bundle: dict[str, Any],
        catalog: str,
        company_name: str,
        spark: Any,
        llm_endpoint: str,
        run_mode: str,
    ) -> dict[str, Any]:
        """The real entry point. Never raises."""
        run_id = uuid.uuid4().hex
        try:
            result = self._score(bundle, company_name, spark, llm_endpoint, run_mode)
        except Exception as exc:  # noqa: BLE001 - MPS must never propagate (§0/§4.2)
            print(f"[mps_agent] unexpected error, degrading: {exc!r}")
            try:
                cim_detected = _cim_detected(bundle)
            except Exception:
                cim_detected = False
            result = _degraded_result(
                run_mode, None, f"unexpected error: {exc!r}", cim_detected, False
            )

        result["catalog"] = catalog
        result["company_name"] = company_name
        result["llm_endpoint"] = llm_endpoint
        result["run_id"] = run_id

        try:
            _write_mps_row(spark, catalog, company_name, llm_endpoint, run_id, result)
        except Exception as exc:  # noqa: BLE001 - persistence must never break rendering
            print(f"[mps_agent] Delta write failed (non-fatal): {exc!r}")

        return result

    def _score(
        self, bundle: dict[str, Any], company_name: str, spark: Any, llm_endpoint: str, run_mode: str
    ) -> dict[str, Any]:
        cim_detected = _cim_detected(bundle)
        growth_mindset_evidence, retrieval_used = _growth_mindset_evidence(
            company_name, spark, cim_detected
        )

        try:
            rubric = load_rubric()
        except RubricError as exc:
            print(f"[mps_agent] rubric load failed, degrading: {exc!r}")
            return _degraded_result(
                run_mode, None, f"rubric load failed: {exc!r}", cim_detected, retrieval_used
            )

        try:
            digest = _build_mps_digest(bundle, growth_mindset_evidence)
            system_prompt = _assemble_system_prompt(rubric)
            raw = self._call_llm(system_prompt, json.dumps(digest), llm_endpoint, max_tokens=_MPS_MAX_TOKENS)
            parsed = self._parse_json_response(raw)
        except Exception as exc:  # noqa: BLE001 - bounded call must never propagate (§7.1)
            print(f"[mps_agent] bounded call failed, degrading: {exc!r}")
            return _degraded_result(
                run_mode, rubric, f"LLM call failed: {exc!r}", cim_detected, retrieval_used
            )

        categories, ok = _reorder_and_validate_categories(parsed, rubric)
        if not ok:
            return _degraded_result(
                run_mode,
                rubric,
                "LLM response missing required shape or a score outside [1,5]",
                cim_detected,
                retrieval_used,
            )

        total = mps_total([c["score"] for c in categories])
        verdict = mps_verdict(total, rubric["threshold"])

        return {
            "mps_status": "success" if total is not None else "partial",
            "rubric_version": rubric["rubric_version"],
            "threshold": rubric["threshold"],
            "run_mode": run_mode,
            "generated_at": _now_iso(),
            "categories": categories,
            "total": total,
            "verdict": verdict,
            "degraded_reason": None,
            "cim_detected": cim_detected,
            "retrieval_used": retrieval_used,
        }
