"""Judge-capability calibration driver (§17 item 26a)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import mlflow.deployments
import yaml
from dotenv import load_dotenv

from eval.content.agreement import (
    compute_metrics,
    compute_sample_composition,
    evaluate_thresholds,
    normalize_unit_magnitude,
)
from eval.content.spot_check import (
    _EXEC_TOP10_RANK_MAP,
    exec_claim_source,
    load_exec_analysis_cache,
)
from eval.retrieval.companies import canonical_company_slug

NUMERIC_SURFACES = frozenset({"fta_numeric"})
NON_NUMERIC_SURFACES = frozenset({"exec_summary", "legal_register"})
CLAIM_VERDICTS = frozenset({"supported", "contradicted", "unsupported"})

VERDICT_SYSTEM_PROMPT = """You are a diligence evidence judge. Given a claim and retrieved evidence chunks,
return ONLY valid JSON with one key:
  "verdict": one of "supported", "contradicted", "unsupported"
Use the §16 vocabulary exactly. Base your verdict only on the supplied evidence."""

EXEC_VERDICT_SYSTEM_PROMPT = """You are a diligence evidence judge. Given a claim and retrieved evidence records,
return ONLY valid JSON with one key:
  "verdict": one of "supported", "contradicted", "unsupported"
Use the §16 vocabulary exactly. Base your verdict only on the supplied evidence.
When evidence includes source_type "analysis_table", prefer that structured analysis-table
record over vector-retrieved VDR chunks when adjudicating."""

VERDICT_USER_TEMPLATE = """Claim (verbatim):
{claim_text}

Retrieved evidence chunks (JSON array):
{evidence_json}

Return JSON: {{"verdict": "<supported|contradicted|unsupported>"}}"""

NUMERIC_SYSTEM_PROMPT = """You are a diligence numeric transcription judge. Given a claim and evidence chunks,
locate the cited evidence and transcribe the numeric value. Return ONLY valid JSON with:
  "extracted_value": {{"magnitude": "<exact decimal string, no separators>", "unit": "<§16 unit>"}} or null
  "cited_span": {{"chunk_id": "<uuid>", "locator": {{"kind": "page|section", "value": "..."}} or null}} or null
Do NOT emit a verdict field. Use §16 units (USD, USD_k, USD_m, USD_bn, percent, ratio, count, days).
Transcribe units from evidence headers; do not convert magnitudes across scales."""

NUMERIC_USER_TEMPLATE = """Claim (verbatim):
{claim_text}

Retrieved evidence chunks (include chunk_id, file_name, page_start, section_header, excerpt):
{evidence_json}

Return JSON with extracted_value and cited_span only."""


class _DecimalLoader(yaml.SafeLoader):
    pass


def _decimal_constructor(loader: yaml.Loader, node: yaml.Node) -> Decimal:
    return Decimal(loader.construct_scalar(node))


_DecimalLoader.add_constructor("tag:yaml.org,2002:float", _decimal_constructor)


def load_sample(path: Path) -> dict[str, Any]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_DecimalLoader)


def _configure_databricks_env() -> None:
    """Align mlflow deployments auth with repo-root .env (DATABRICKS_SERVER_HOSTNAME)."""
    host = os.environ.get("DATABRICKS_SERVER_HOSTNAME")
    if host and not os.environ.get("DATABRICKS_HOST"):
        os.environ["DATABRICKS_HOST"] = host


def _workspace_client():
    from databricks.sdk import WorkspaceClient

    _configure_databricks_env()
    return WorkspaceClient(
        host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        token=os.environ["DATABRICKS_TOKEN"],
    )


def _warehouse_id() -> str:
    return os.environ["DATABRICKS_HTTP_PATH"].rstrip("/").split("/")[-1]


def _sql(w, statement: str) -> list[list[str]]:
    stmt = w.statement_execution.execute_statement(
        warehouse_id=_warehouse_id(),
        statement=statement,
        wait_timeout="50s",
    )
    state = stmt.status.state.value if stmt.status else "UNKNOWN"
    if state != "SUCCEEDED":
        raise RuntimeError(f"SQL failed ({state}): {statement[:200]}")
    return stmt.result.data_array if stmt.result else []


def verify_chunk_ids(
    w,
    *,
    catalog: str,
    company: str,
    chunk_ids: list[str],
) -> list[str]:
    """Return chunk_ids missing from corpus (kill criterion 3)."""
    if not chunk_ids:
        return []
    in_list = ", ".join(f"'{cid}'" for cid in chunk_ids)
    rows = _sql(
        w,
        f"""
        SELECT chunk_id
        FROM {catalog}.ingestion.chunks
        WHERE company_name = '{company.replace("'", "''")}'
          AND chunk_id IN ({in_list})
        """,
    )
    found = {r[0] for r in rows}
    return [cid for cid in chunk_ids if cid not in found]


def fetch_chunk_metadata(
    w,
    *,
    catalog: str,
    company: str,
    chunk_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not chunk_ids:
        return {}
    in_list = ", ".join(f"'{cid}'" for cid in chunk_ids)
    rows = _sql(
        w,
        f"""
        SELECT chunk_id, file_name, page_start, section_header,
               SUBSTRING(chunk_text, 1, 1200) AS excerpt
        FROM {catalog}.ingestion.chunks
        WHERE company_name = '{company.replace("'", "''")}'
          AND chunk_id IN ({in_list})
        """,
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[row[0]] = {
            "chunk_id": row[0],
            "file_name": row[1],
            "page_start": int(row[2]) if row[2] not in (None, "") else None,
            "section_header": row[3],
            "excerpt": row[4],
        }
    return out


def retrieve_evidence(
    w,
    *,
    catalog: str,
    company: str,
    query: str,
    top_k: int = 5,
    embedding_endpoint: str = "databricks-bge-large-en",
) -> list[dict[str, Any]]:
    _configure_databricks_env()
    embed_client = mlflow.deployments.get_deploy_client("databricks")
    embed_resp = embed_client.predict(
        endpoint=embedding_endpoint,
        inputs={"input": [query]},
    )
    query_vector = embed_resp["data"][0]["embedding"]

    resp = w.vector_search_indexes.query_index(
        index_name=f"{catalog}.ingestion.embeddings_index",
        columns=["chunk_id"],
        query_vector=query_vector,
        num_results=top_k,
        filters_json=json.dumps({"company_name": company}),
    )
    chunk_ids = [row[0] for row in (resp.result.data_array if resp.result else [])]
    if not chunk_ids:
        return []

    in_list = ", ".join(f"'{cid}'" for cid in chunk_ids)
    rows = _sql(
        w,
        f"""
        SELECT c.chunk_id, c.file_name, c.page_start, c.section_header,
               SUBSTRING(c.chunk_text, 1, 1200) AS excerpt,
               r.workstream
        FROM {catalog}.ingestion.chunks c
        LEFT JOIN {catalog}.classification.doc_relevance r
          ON c.doc_id = r.doc_id
        WHERE c.company_name = '{company.replace("'", "''")}'
          AND c.chunk_id IN ({in_list})
        """,
    )
    order = {cid: idx for idx, cid in enumerate(chunk_ids)}
    records = []
    for row in rows:
        record = {
            "chunk_id": row[0],
            "file_name": row[1],
            "page_start": int(row[2]) if row[2] not in (None, "") else None,
            "section_header": row[3],
            "excerpt": row[4],
            "workstream": row[5],
        }
        records.append(record)
    records.sort(key=lambda r: order.get(r["chunk_id"], 999))
    return records


def _fta_rows_for_location(
    rows: list[dict[str, Any]], *, location_contains: str
) -> list[dict[str, Any]]:
    needle = location_contains.lower()
    return [
        row
        for row in rows
        if needle in str(row.get("source_location") or "").lower()
    ]


def _qoe_ledger_item(ledger: list[dict[str, Any]], letter: str) -> dict[str, Any] | None:
    tag = f"[{letter.upper()}]"
    for row in ledger:
        desc = str(row.get("description") or "")
        if desc.startswith(tag) or f" {tag}" in desc:
            return row
    return None


def _top10_issue_by_rank(
    issues: list[dict[str, Any]], rank: int
) -> dict[str, Any] | None:
    for issue in issues:
        if int(issue.get("rank") or 0) == rank:
            return issue
    return None


def exec_claim_analysis_evidence(
    claim_id: str,
    cache: dict[str, Any],
    *,
    company_slug: str,
) -> dict[str, Any] | None:
    """Return structured analysis-table evidence for exec_summary judge calibration."""

    source_doc, source_location = exec_claim_source(
        claim_id, cache, company_slug=company_slug
    )
    revenue = cache.get("revenue_trend_json") or []
    ledger = cache.get("addback_ledger_json") or []
    top10 = cache.get("top_10_issues_json") or []

    table: str | None = None
    field: str | None = None
    payload: Any = None

    if claim_id in {"exec.claim.003", "exec.claim.004", "exec.claim.020"}:
        table, field = "kpi", "healthcare_kpis_json"
        payload = cache.get("healthcare_kpis_json")
        if claim_id == "exec.claim.004":
            table, field = "business_model", "customer_operational_metrics_json"
            payload = {
                "healthcare_kpis_json": cache.get("healthcare_kpis_json"),
                "customer_operational_metrics_json": cache.get(
                    "customer_operational_metrics_json"
                ),
            }
    elif claim_id in {
        "exec.claim.007",
        "exec.claim.008",
        "exec.claim.009",
        "exec.claim.010",
        "exec.claim.012",
    }:
        table, field = "financial_trends", "revenue_trend_json"
        payload = {
            "revenue_trend_json": _fta_rows_for_location(
                revenue, location_contains="Historical P&L Summary"
            ),
            "ebitda_json": cache.get("ebitda_json"),
            "addback_pct_of_ebitda": cache.get("addback_pct_of_ebitda"),
        }
    elif claim_id == "exec.claim.011":
        table, field = "quality_of_earnings", "addback_ledger_json"
        payload = {
            "tier4_addback_count": cache.get("tier4_addback_count"),
            "addback_ledger_json": ledger,
        }
    elif claim_id == "exec.claim.013":
        table, field = "quality_of_earnings", "addback_ledger_json"
        payload = ledger
    elif claim_id in {"exec.claim.014", "exec.claim.015", "exec.claim.016"}:
        letter = {"exec.claim.014": "G", "exec.claim.015": "K", "exec.claim.016": "O"}[
            claim_id
        ]
        item = _qoe_ledger_item(ledger, letter)
        if item is None:
            return None
        table, field = "quality_of_earnings", "addback_ledger_json"
        payload = item
    elif claim_id == "exec.claim.017":
        table, field = "diligence_report", "reconciliation_summary_json"
        payload = cache.get("reconciliation_summary_json")
    elif claim_id == "exec.claim.018":
        table, field = "forecast", "forecast_assumptions_json"
        payload = {
            "forecast_assumptions_json": cache.get("forecast_assumptions_json"),
            "credibility_summary_json": cache.get("credibility_summary_json"),
        }
    elif claim_id == "exec.claim.019":
        table, field = "diligence_report", "section_ratings_json"
        payload = cache.get("section_ratings_json")
    elif claim_id in {"exec.claim.025", "exec.claim.026"}:
        table, field = "diligence_report", "section_confidence_json"
        payload = {
            "section_confidence_json": cache.get("section_confidence_json"),
            "section_ratings_json": cache.get("section_ratings_json"),
        }
    elif claim_id in _EXEC_TOP10_RANK_MAP:
        rank = _EXEC_TOP10_RANK_MAP[claim_id]
        issue = _top10_issue_by_rank(top10, rank)
        if issue is None:
            return None
        table, field = "diligence_report", "top_10_issues_json"
        payload = issue
    elif claim_id == "exec.claim.028":
        table, field = "quality_of_earnings", "addback_ledger_json"
        payload = {
            "qofe_report_present": cache.get("qofe_report_present"),
            "tier4_addback_count": cache.get("tier4_addback_count"),
            "addback_ledger_json": ledger,
        }
    elif claim_id == "exec.claim.027":
        table, field = "kpi", "healthcare_kpis_json"
        payload = cache.get("healthcare_kpis_json")

    if payload is None:
        return None

    return {
        "source_type": "analysis_table",
        "analysis_table": table,
        "field": field,
        "source_doc": source_doc,
        "source_location": source_location,
        "payload": payload,
    }


def build_exec_dual_source_evidence(
    w,
    *,
    claim_id: str,
    claim_text: str,
    cache: dict[str, Any],
    company_slug: str,
    catalog: str,
    company: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Merge analysis-table evidence with vector-retrieved VDR chunks for exec_summary."""

    analysis = exec_claim_analysis_evidence(
        claim_id, cache, company_slug=company_slug
    )
    chunks = retrieve_evidence(
        w, catalog=catalog, company=company, query=claim_text, top_k=top_k
    )
    if analysis is not None:
        return [analysis, *chunks]
    return chunks


def call_llm(*, endpoint: str, system_prompt: str, user_prompt: str) -> str:
    _configure_databricks_env()
    client = mlflow.deployments.get_deploy_client("databricks")
    response = client.predict(
        endpoint=endpoint,
        inputs={
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 2048,
            "temperature": 0.0,
        },
    )
    return response["choices"][0]["message"]["content"]


def _parse_json_response(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def call_llm_with_retry(
    *,
    endpoint: str,
    system_prompt: str,
    user_prompt: str,
    retries: int = 3,
) -> str:
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            return call_llm(
                endpoint=endpoint,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # noqa: BLE001 — retry bounded infra failures
            last_err = exc
    raise RuntimeError(f"LLM call failed after {retries} retries") from last_err


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def apply_three_branch_locator(
    chunk_meta: dict[str, Any] | None,
    locator: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Operator C3 / HALT-33/34 authoring rule for expected_span.locator labels.

    Used when authoring calibration samples (operator-side). Has no judge-side role:
    judge locators are compared as emitted per plan §2 A-C4.
    """
    if chunk_meta is None:
        return locator
    section = chunk_meta.get("section_header")
    page = chunk_meta.get("page_start")
    if section:
        return {"kind": "section", "value": section}
    if page is not None:
        return {"kind": "page", "value": page}
    return None


def _extracted_value_parseable(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if isinstance(value.get("magnitude"), float):
        return False
    return normalize_unit_magnitude(value.get("magnitude"), value.get("unit")) is not None


def parse_verdict_response(raw: str) -> dict[str, Any]:
    """Parse non-numeric judge JSON; fail-closed per A-EE."""
    try:
        parsed = _parse_json_response(raw)
    except json.JSONDecodeError:
        return {"verdict": None, "parse_failure": True}
    verdict = parsed.get("verdict")
    if verdict not in CLAIM_VERDICTS:
        return {"verdict": None, "parse_failure": True}
    return {"verdict": verdict, "parse_failure": False}


def parse_numeric_judge_response(raw: str) -> dict[str, Any]:
    """Parse numeric judge JSON; fail-closed on malformed or unparseable extraction."""
    try:
        parsed = _parse_json_response(raw)
    except json.JSONDecodeError:
        return {"extracted_value": None, "cited_span": None, "parse_failure": True}
    extracted = parsed.get("extracted_value")
    if extracted is not None and not _extracted_value_parseable(extracted):
        return {"extracted_value": None, "cited_span": None, "parse_failure": True}
    cited = parsed.get("cited_span")
    if cited is not None and not isinstance(cited, dict):
        return {"extracted_value": None, "cited_span": None, "parse_failure": True}
    return {
        "extracted_value": extracted,
        "cited_span": cited,
        "parse_failure": False,
    }


def judge_claim(
    *,
    surface: str,
    claim: dict[str, Any],
    evidence: list[dict[str, Any]],
    endpoint: str,
    chunk_meta_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    claim_text = claim.get("claim_text", "")
    if surface in NUMERIC_SURFACES:
        raw = call_llm_with_retry(
            endpoint=endpoint,
            system_prompt=NUMERIC_SYSTEM_PROMPT,
            user_prompt=NUMERIC_USER_TEMPLATE.format(
                claim_text=claim_text,
                evidence_json=json.dumps(evidence, indent=2),
            ),
        )
        parsed = parse_numeric_judge_response(raw)
        return {**parsed, "raw_response": raw}

    verdict_prompt = (
        EXEC_VERDICT_SYSTEM_PROMPT if surface == "exec_summary" else VERDICT_SYSTEM_PROMPT
    )
    raw = call_llm_with_retry(
        endpoint=endpoint,
        system_prompt=verdict_prompt,
        user_prompt=VERDICT_USER_TEMPLATE.format(
            claim_text=claim_text,
            evidence_json=json.dumps(evidence, indent=2),
        ),
    )
    parsed = parse_verdict_response(raw)
    return {**parsed, "raw_response": raw}


def run_calibration(
    *,
    surface: str,
    sample_path: Path,
    company: str,
    catalog: str,
    endpoint: str,
) -> dict[str, Any]:
    load_dotenv(_repo_root() / ".env")
    sample = load_sample(sample_path)
    if sample.get("surface") != surface:
        raise ValueError(
            f"sample surface {sample.get('surface')!r} != --surface {surface!r}"
        )

    w = _workspace_client()

    chunk_ids = [
        (c.get("expected_span") or {}).get("chunk_id")
        for c in sample.get("claims") or []
        if (c.get("expected_span") or {}).get("chunk_id")
    ]
    missing = verify_chunk_ids(w, catalog=catalog, company=company, chunk_ids=chunk_ids)
    if missing:
        raise RuntimeError(
            f"chunk resolution guard failed for {surface}: missing chunk_ids {missing}"
        )

    chunk_meta_by_id = fetch_chunk_metadata(
        w, catalog=catalog, company=company, chunk_ids=chunk_ids
    )

    exec_analysis_cache: dict[str, Any] | None = None
    company_slug = canonical_company_slug(company)
    if surface == "exec_summary":
        exec_analysis_cache = load_exec_analysis_cache(
            lambda stmt: _sql(w, stmt),
            catalog=catalog,
            company=company,
        )

    judge_outputs: list[dict[str, Any]] = []
    per_claim: list[dict[str, Any]] = []
    parse_failures = 0
    for idx, claim in enumerate(sample.get("claims") or [], start=1):
        query = claim.get("claim_text", "")
        claim_id = str(claim.get("claim_id") or "")
        print(f"[{surface}] claim {idx}/{len(sample.get('claims') or [])} {claim.get('claim_id')}", flush=True)
        if surface == "exec_summary" and exec_analysis_cache is not None:
            evidence = build_exec_dual_source_evidence(
                w,
                claim_id=claim_id,
                claim_text=query,
                cache=exec_analysis_cache,
                company_slug=company_slug,
                catalog=catalog,
                company=company,
                top_k=5,
            )
        else:
            evidence = retrieve_evidence(
                w, catalog=catalog, company=company, query=query, top_k=5
            )
        retrieved_chunk_ids = [
            e["chunk_id"] for e in evidence if e.get("source_type") != "analysis_table"
        ]
        analysis_evidence = next(
            (e for e in evidence if e.get("source_type") == "analysis_table"), None
        )
        output = judge_claim(
            surface=surface,
            claim=claim,
            evidence=evidence,
            endpoint=endpoint,
            chunk_meta_by_id=chunk_meta_by_id,
        )
        if output.get("parse_failure"):
            parse_failures += 1
        judge_outputs.append(output)
        per_claim.append(
            {
                "claim_id": claim.get("claim_id"),
                "operator_verdict": claim.get("verdict"),
                "retrieved_chunk_ids": retrieved_chunk_ids,
                "analysis_evidence": analysis_evidence,
                "judge_output": {
                    k: v
                    for k, v in output.items()
                    if k not in ("raw_response", "parse_failure")
                },
                "raw_response": output.get("raw_response", ""),
            }
        )

    figures = compute_metrics(sample, judge_outputs, surface=surface)
    threshold_result = evaluate_thresholds(
        surface,
        figures,
        sample_composition=compute_sample_composition(sample),
    )

    return {
        "surface": surface,
        "company": company,
        "catalog": catalog,
        "endpoint": endpoint,
        "sample_path": str(sample_path),
        "claim_count": len(sample.get("claims") or []),
        "figures": figures,
        "passed": threshold_result.passed,
        "failure_reasons": threshold_result.failure_reasons,
        "unevaluated_pins": threshold_result.unevaluated_pins,
        "rung_assignment": "judge" if threshold_result.passed else "human",
        "prompts": {
            "numeric_system": NUMERIC_SYSTEM_PROMPT if surface in NUMERIC_SURFACES else None,
            "verdict_system": (
                EXEC_VERDICT_SYSTEM_PROMPT
                if surface == "exec_summary"
                else VERDICT_SYSTEM_PROMPT
                if surface not in NUMERIC_SURFACES
                else None
            ),
        },
        "evidence_mode": "dual_source" if surface == "exec_summary" else "chunk_rag",
        "parse_failures": parse_failures,
        "per_claim": per_claim,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Judge-capability calibration (item 26a)")
    parser.add_argument("--surface", required=True)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--company", default="Elder Care")
    parser.add_argument("--catalog", default="uc13_ale")
    parser.add_argument("--endpoint", default="databricks-claude-sonnet-4-6")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    load_dotenv(_repo_root() / ".env")
    result = run_calibration(
        surface=args.surface,
        sample_path=args.sample,
        company=args.company,
        catalog=args.catalog,
        endpoint=args.endpoint,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"surface": result["surface"], "passed": result["passed"], "figures": result["figures"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
