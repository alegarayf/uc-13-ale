"""CHK-27 exec_summary LLM-judge harness — production rung-2 build (§17 item 27).

Post-T12 build slice (``OI-eval-content-exec-summary-judge-rung-build``): reuses
``judge_claim`` / ``build_exec_dual_source_evidence`` (``calibration.py``) and
``S2Writer`` (``s2_writer.py``) verbatim. Claim enumeration is imported from
``spot_check.load_claim_enumeration`` — no duplicate manifest-parsing logic.

This module (plan T5) only builds and dry-run-verifies the harness; an at-scale
production run against ``uc13_ale.eval.s2_scores`` is a downstream subtask's
exclusive scope (plan T6). ``run_judge_harness`` defaults to ``dry_run=True``
(enumerate + judge, no S2 writes) for exactly this reason.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from eval.content.calibration import (
    _workspace_client,
    build_exec_dual_source_evidence,
    judge_claim,
)
from eval.content.legal_register_verifier import make_warehouse_chunk_id_resolver
from eval.content.s2_writer import (
    ChunkIdResolver,
    S2ScoreRow,
    S2Writer,
    SqlExecutor,
    make_sdk_sql_executor,
)
from eval.content.spot_check import (
    CLAIM_VERDICTS,
    ChunkIndex,
    SpotCheckClaim,
    SpotCheckConfig,
    _generate_run_id,
    load_claim_enumeration,
    load_exec_analysis_cache,
)
from eval.retrieval.companies import canonical_company_slug

JUDGE_HARNESS_SURFACE = "exec_summary"
JUDGE_HARNESS_WRITER = "judge_harness"
JUDGE_HARNESS_RUNG = 2
DEFAULT_ENDPOINT = "databricks-claude-sonnet-4-6"
DEFAULT_CATALOG = "uc13_ale"
DEFAULT_COMPANY = "Elder Care"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class JudgeHarnessResult:
    """Outcome of one judge-harness run — dry-run (build/verify) or production write."""

    run_id: str
    run_ts: datetime
    claim_count: int
    written_count: int
    parse_failures: int
    verdict_counts: dict[str, int]


def _rationale_from_output(output: dict[str, Any]) -> str:
    """Derive a non-null S2 rationale from the judge's raw response.

    ``calibration.py``'s verdict prompts (reused verbatim, not modified here) ask
    for verdict JSON only — no rationale field. The raw model response text is the
    only signal available without changing that prompt contract, so it doubles as
    this row's rationale.
    """
    raw = str(output.get("raw_response") or "").strip()
    if raw:
        return raw
    return f"judge_harness: verdict {output.get('verdict')!r} (no rationale text returned)"


def judge_claims(
    w,
    *,
    claims: tuple[SpotCheckClaim, ...],
    exec_analysis_cache: dict[str, Any],
    company_slug: str,
    catalog: str,
    company: str,
    endpoint: str,
) -> list[dict[str, Any]]:
    """Judge every enumerated claim; returns one ``{claim, judge_output}`` dict per claim."""
    results: list[dict[str, Any]] = []
    for claim in claims:
        evidence = build_exec_dual_source_evidence(
            w,
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            cache=exec_analysis_cache,
            company_slug=company_slug,
            catalog=catalog,
            company=company,
        )
        output = judge_claim(
            surface=JUDGE_HARNESS_SURFACE,
            claim={"claim_text": claim.claim_text},
            evidence=evidence,
            endpoint=endpoint,
            chunk_meta_by_id={},
        )
        results.append({"claim": claim, "judge_output": output})
    return results


def build_claim_rows(
    company_slug: str,
    run_id: str,
    run_ts: datetime,
    judged: list[dict[str, Any]],
) -> tuple[list[S2ScoreRow], int]:
    """Map judged claims to valid ``S2ScoreRow`` objects.

    Fail-closed (S-61/A-EE precedent): a claim whose judge output failed to parse,
    or whose verdict is outside the §16 vocabulary, is excluded from the write set
    rather than written with an invalid/null verdict. Excluded claims are counted
    in ``parse_failures`` for the caller to gate on.
    """
    rows: list[S2ScoreRow] = []
    parse_failures = 0
    for item in judged:
        claim: SpotCheckClaim = item["claim"]
        output = item["judge_output"]
        verdict = output.get("verdict")
        if output.get("parse_failure") or verdict not in CLAIM_VERDICTS:
            parse_failures += 1
            continue
        rows.append(
            S2ScoreRow(
                company=company_slug,
                surface=JUDGE_HARNESS_SURFACE,
                run_id=run_id,
                run_ts=run_ts,
                row_type="claim",
                claim_id=claim.claim_id,
                verdict=verdict,
                rationale=_rationale_from_output(output),
                writer=None,
                asserted_magnitude=claim.asserted_magnitude,
                asserted_unit=claim.asserted_unit,
                extracted_magnitude=None,
                extracted_unit=None,
                cited_chunk_id=claim.cited_chunk_id,
                cited_locator_kind=claim.cited_locator_kind,
                cited_locator_value=claim.cited_locator_value,
                judge_verdict_advisory=None,
            )
        )
    return rows, parse_failures


def _enumerate_claims(
    *,
    company: str,
    catalog: str,
    sql_executor: SqlExecutor | None,
) -> tuple[tuple[SpotCheckClaim, ...], dict[str, Any]]:
    exec_analysis_cache = (
        load_exec_analysis_cache(sql_executor, catalog=catalog, company=company)
        if sql_executor is not None
        else {}
    )
    chunk_index = (
        ChunkIndex.from_sql(sql_executor, catalog=catalog, company=company)
        if sql_executor is not None
        else None
    )
    config = SpotCheckConfig(
        company=company,
        surface=JUDGE_HARNESS_SURFACE,
        source="analysis.diligence_report",
        output_dir=Path("."),
        verdicts_path=Path("."),
        operator_id=JUDGE_HARNESS_WRITER,
        catalog=catalog,
    )
    claims = load_claim_enumeration(
        config, chunk_index=chunk_index, exec_analysis_cache=exec_analysis_cache
    )
    return claims, exec_analysis_cache


def run_judge_harness(
    *,
    company: str = DEFAULT_COMPANY,
    catalog: str = DEFAULT_CATALOG,
    endpoint: str = DEFAULT_ENDPOINT,
    dry_run: bool = True,
    w: Any = None,
    writer: S2Writer | None = None,
    sql_executor: SqlExecutor | None = None,
    chunk_id_resolver: ChunkIdResolver | None = None,
    claims: tuple[SpotCheckClaim, ...] | None = None,
    exec_analysis_cache: dict[str, Any] | None = None,
    run_id: str | None = None,
    run_ts: datetime | None = None,
) -> JudgeHarnessResult:
    """Enumerate, judge, and (unless ``dry_run``) write one exec_summary rung-2 run.

    ``dry_run=True`` (default) enumerates and judges claims without writing to S2 —
    at-scale production writes are plan T6's exclusive scope, not this subtask's.
    """
    company_slug = canonical_company_slug(company)
    w = w if w is not None else _workspace_client()

    if claims is None or exec_analysis_cache is None:
        enumerated_claims, enumerated_cache = _enumerate_claims(
            company=company, catalog=catalog, sql_executor=sql_executor
        )
        claims = claims if claims is not None else enumerated_claims
        exec_analysis_cache = (
            exec_analysis_cache if exec_analysis_cache is not None else enumerated_cache
        )

    judged = judge_claims(
        w,
        claims=claims,
        exec_analysis_cache=exec_analysis_cache,
        company_slug=company_slug,
        catalog=catalog,
        company=company,
        endpoint=endpoint,
    )

    if run_id is not None and run_ts is not None:
        resolved_run_id, resolved_run_ts = run_id, run_ts
    else:
        resolved_run_id, resolved_run_ts = _generate_run_id(run_ts)

    rows, parse_failures = build_claim_rows(
        company_slug, resolved_run_id, resolved_run_ts, judged
    )

    verdict_counts: dict[str, int] = {}
    for row in rows:
        verdict_counts[row.verdict] = verdict_counts.get(row.verdict, 0) + 1

    written_count = 0
    if not dry_run:
        s2_writer = writer or S2Writer(catalog=catalog, sql_executor=sql_executor)
        s2_writer.write_claims(
            company_slug,
            JUDGE_HARNESS_SURFACE,
            resolved_run_id,
            resolved_run_ts,
            rows,
            rationale_required=True,
            rung=JUDGE_HARNESS_RUNG,
            chunk_id_resolver=chunk_id_resolver,
        )
        s2_writer.write_completion_marker(
            company_slug,
            JUDGE_HARNESS_SURFACE,
            resolved_run_id,
            resolved_run_ts,
            JUDGE_HARNESS_WRITER,
        )
        written_count = len(rows)

    return JudgeHarnessResult(
        run_id=resolved_run_id,
        run_ts=resolved_run_ts,
        claim_count=len(claims),
        written_count=written_count,
        parse_failures=parse_failures,
        verdict_counts=verdict_counts,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "CHK-27 exec_summary judge harness (§17 item 27). Defaults to a dry run "
            "(enumerate + judge, no S2 writes); pass --execute for a production write."
        )
    )
    parser.add_argument("--company", default=DEFAULT_COMPANY)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write S2 claim rows + completion marker for real (default: dry-run only).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    load_dotenv(_repo_root() / ".env")
    sql_executor = make_sdk_sql_executor()
    chunk_id_resolver = make_warehouse_chunk_id_resolver(
        catalog=args.catalog, sql_executor=sql_executor
    )
    result = run_judge_harness(
        company=args.company,
        catalog=args.catalog,
        endpoint=args.endpoint,
        dry_run=not args.execute,
        sql_executor=sql_executor,
        chunk_id_resolver=chunk_id_resolver,
    )
    print(
        f"run_id={result.run_id} claims={result.claim_count} "
        f"written={result.written_count} parse_failures={result.parse_failures} "
        f"verdicts={result.verdict_counts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
