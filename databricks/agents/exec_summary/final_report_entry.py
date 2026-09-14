"""Final diligence report bridge — the sibling of ``rainmaker_entry.py``.

Wires the final report layer (``final_report_view`` +
``final_report_narrative`` (T11) + ``renderers.render_final_report``) into
any caller that has already run the 7 workstream agents for
``company_name`` — both VDR branches call this same function so the final
report is produced through one code path regardless of which one ran.

Must be called AFTER the agent DAG has completed for ``company_name`` (same
precondition as ``build_rainmaker_summary``) — ``BundleBuilder`` reads
per-agent ``{catalog}.analysis.*`` Delta rows that only exist once the
agents have run. **Never raises**: every internal failure degrades the
affected piece and is reported through the return value, mirroring
``build_rainmaker_summary``'s contract.
"""

from __future__ import annotations

import json
import traceback
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


def _load_prior_mps_runs(
    spark: "SparkSession",
    catalog: str,
    company_name: str,
    run_modes: tuple[str, ...] = ("cim_only",),
) -> list[dict[str, Any]]:
    """Read back the newest MPS run per ``run_mode`` from
    ``{catalog}.analysis.mps_score`` (append-only — ``mps_agent.py:454-488``),
    rehydrated into the shape ``rainmaker_view._mps_table`` consumes.

    One helper, two callers: Branch A passes ``("cim_only",)`` to recover the
    *prior* column that renders alongside the current full-room run; Branch B
    passes ``("full_vdr_no_cim",)`` to recover the run it will *reuse*
    (``reuse_mps_run`` below, decision D-02). Same query, different caller
    intent.

    Returns runs ordered **oldest-first**, so the caller can simply append
    the current run last. ``degraded_reason`` is not a persisted column, so a
    rehydrated run always carries ``degraded_reason=None`` — harmless,
    because ``_mps_table`` only reads that field off ``mps_runs[-1]`` and a
    prior run recovered here is never last.

    Never raises. A missing table, an empty result, or a malformed
    ``categories_json`` all collapse to ``[]`` with a printed reason — a
    missing prior column is a cosmetic loss on the page; a crash here would
    cost the whole final report.
    """
    if not run_modes:
        return []

    table = f"{catalog}.analysis.mps_score"
    try:
        placeholders = ", ".join(f":m{i}" for i in range(len(run_modes)))
        args: dict[str, Any] = {"c": company_name}
        for i, run_mode in enumerate(run_modes):
            args[f"m{i}"] = run_mode

        rows = spark.sql(
            f"SELECT * FROM {table} WHERE company_name = :c AND run_mode IN ({placeholders}) "
            "ORDER BY generated_at DESC",
            args=args,
        ).collect()

        newest_by_mode: dict[str, dict[str, Any]] = {}
        for row in rows:
            row_dict = row.asDict()
            run_mode = row_dict.get("run_mode")
            if run_mode not in newest_by_mode:
                newest_by_mode[run_mode] = row_dict

        runs: list[dict[str, Any]] = []
        for run_mode in run_modes:
            row_dict = newest_by_mode.get(run_mode)
            if row_dict is None:
                continue
            generated_at = row_dict.get("generated_at")
            runs.append(
                {
                    "run_mode": run_mode,
                    # generated_at is a TIMESTAMP column; _mps_column_header
                    # slices str(...)[:10], so it must be converted to an
                    # ISO-ish string explicitly rather than relying on
                    # whatever the driver's str() happens to produce.
                    "generated_at": str(generated_at) if generated_at is not None else None,
                    "categories": json.loads(row_dict.get("categories_json") or "[]"),
                    "threshold": row_dict.get("threshold"),
                    "mps_status": row_dict.get("mps_status"),
                    "total": row_dict.get("total"),
                    "verdict": row_dict.get("verdict"),
                }
            )

        runs.sort(key=lambda run: run["generated_at"] or "")
        return runs
    except Exception as exc:  # noqa: BLE001 - a prior-run read-back must never break the final report
        print(f"[final_report] prior MPS read-back from {table} failed (non-fatal), no prior run available: {exc!r}")
        return []


def _load_forecast(spark: "SparkSession", catalog: str, company_name: str) -> dict[str, Any]:
    """``{"forecast_rows": [...], "forecast_assumptions": [...]}`` read back
    from ``{catalog}.analysis.forecast`` (decision D-03).

    ``forecast_agent.py`` extracts everything page 8 wants, but
    ``BundleBuilder`` never reads that table (``constants.py:4-11`` omits
    ``forecast``), so the data exists in Delta and never reaches the bundle.
    This function resolves that gap here, in a module we own, rather than in
    the shared bundle layer — the caller merges the result into *its own
    copy* of the bundle, leaving ``bundle_builder.py`` and the executive
    review's bundle untouched.

    ``forecast_rows[].ebitda_margin_pct`` is deliberately never populated:
    nothing in the pipeline projects margin (plan §1.7), and substituting
    the historical margin would invent a management commitment that was
    never made. The chart's absence-of-margin footnote is added separately,
    in ``final_report_view._forecast``.

    Never raises: a missing table, an empty result, or malformed JSON all
    return ``{}`` — page 8 renders its "not extracted" state, which is the
    honest degradation.
    """
    table = f"{catalog}.analysis.forecast"
    try:
        rows = spark.sql(
            f"SELECT * FROM {table} WHERE company_name = :c ORDER BY created_at DESC LIMIT 1",
            args={"c": company_name},
        ).collect()
        if not rows:
            return {}
        row_dict = rows[0].asDict()

        revenue_build = json.loads(row_dict.get("revenue_build_comparison_json") or "[]")
        assumptions_raw = json.loads(row_dict.get("forecast_assumptions_json") or "[]")
        mgmt_items = json.loads(row_dict.get("management_validation_items_json") or "[]")

        forecast_rows = [
            {
                "year": rec.get("period"),
                "revenue": rec.get("forecast_revenue"),
                # ebitda_margin_pct: intentionally absent. See docstring.
            }
            for rec in revenue_build
            if isinstance(rec, dict)
        ]

        # management_validation_items carry a "related_assumption" back to
        # the assumption's assumption_type — the only join key the two lists
        # share (forecast_agent.py:871-879).
        mgmt_by_assumption_type: dict[str, dict[str, Any]] = {}
        for item in mgmt_items:
            if isinstance(item, dict) and item.get("related_assumption") is not None:
                mgmt_by_assumption_type.setdefault(item["related_assumption"], item)

        forecast_assumptions = []
        for assumption in assumptions_raw:
            if not isinstance(assumption, dict):
                continue
            entry: dict[str, Any] = {
                "assumption": assumption.get("description") or assumption.get("stated_value"),
                "support": assumption.get("credibility_rating"),
            }
            matching_validation = mgmt_by_assumption_type.get(assumption.get("assumption_type"))
            if matching_validation is not None:
                entry["test"] = matching_validation.get("item")
            forecast_assumptions.append(entry)

        return {"forecast_rows": forecast_rows, "forecast_assumptions": forecast_assumptions}
    except Exception as exc:  # noqa: BLE001 - a forecast read-back must never break the final report
        print(f"[final_report] forecast read-back from {table} failed (non-fatal), page 8 renders 'not extracted': {exc!r}")
        return {}


def build_final_report(
    company_name: str,
    catalog: str,
    spark: "SparkSession",
    llm_endpoint: str,
    run_mode: str,
    prior_mps_runs: list[dict[str, Any]] | None = None,
    reuse_mps_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the final diligence report from a completed agent run.

    Wraps, in order: ``BundleBuilder().build`` → ``validate_bundle`` →
    ``verify_bundle_claims`` → merge D-03's forecast read-back →
    ``synthesize_rainmaker_narrative`` → ``MPSAgent().score`` (or
    ``reuse_mps_run``, see below) → ``render_final_report``. Never raises.

    ``run_mode`` is a fact about which VDR branch the *caller* took — it
    must never be re-derived from ``bundle.meta`` (``bundle_builder.py:
    652-668`` confirms that key does not exist). Passed straight through to
    ``MPSAgent().score`` and to ``render_final_report``.

    ``reuse_mps_run`` (decision D-02 — a deliberate deviation from §2.3 of
    the task prompt, which says the final report's MPS is *always* a fresh
    ``MPSAgent().score()`` call): pass the *already-scored* MPS run for this
    exact bundle to skip a redundant LLM call over identical data. This is
    only ever correct when the caller knows **no new evidence** entered the
    bundle since that run was scored — Branch B, where the executive review
    and the final report share one bundle with no ingestion and no agent run
    in between. Passing it on Branch A would be a bug: the whole point there
    is that more was read after the executive review shipped.

    A non-``None`` but empty/malformed ``reuse_mps_run`` (the read-back
    found nothing — a missing table, an executive review whose MPS never
    persisted) falls back to a fresh ``MPSAgent().score()`` call rather than
    rendering an empty MPS page; that fallback is a degraded path and is
    reported as such via ``mps_source``.

    Returns::

        {
            "status": "success" | "degraded" | "failed",
            "html": path | None,
            "pdf": path | None,
            "pdf_degraded": bool,
            "synthesis_status": str | None,
            "final_narrative_status": str | None,
            "mps_status": str | None,
            "mps_source": "reused" | "scored" | "scored_fallback" | None,
            "error": str | None,
        }
    """
    try:
        from agents.exec_summary.absence_check import verify_bundle_claims
        from agents.exec_summary.bundle_builder import BundleBuilder
        from agents.exec_summary.final_report_narrative import synthesize_final_report_narrative
        from agents.exec_summary.rainmaker_narrative import synthesize_rainmaker_narrative
        from agents.exec_summary.renderers import render_final_report
        from agents.exec_summary.validate import validate_bundle
        from agents.workstreams.mps_agent import MPSAgent

        bundle = BundleBuilder().build(company_name, catalog, spark, llm_endpoint)
        validate_bundle(bundle)

        checked = verify_bundle_claims(bundle, spark, catalog, company_name)

        forecast = _load_forecast(spark, catalog, company_name)
        if forecast:
            financials = dict(checked.get("financials") or {})
            financials.update(forecast)
            checked = {**checked, "financials": financials}

        er_narrative = synthesize_rainmaker_narrative(checked, llm_endpoint, spark)
        fr_narrative = synthesize_final_report_narrative(checked, llm_endpoint, spark)
        # The section layer wins on the single overlapping key
        # (`recommendation`): the ER returns a sentence, T11's structured
        # dict is the shape the template reads. Do not "fix" this order —
        # {**er, **fr} means fr's keys win, which is deliberate.
        narrative = {**er_narrative, **fr_narrative}
        print(
            f"[final_report] narrative synthesis: er={er_narrative.get('synthesis_status')} "
            f"final={fr_narrative.get('final_narrative_status')}"
        )

        if reuse_mps_run is not None and reuse_mps_run:
            mps = reuse_mps_run
            mps_source = "reused"
            print(
                f"[final_report] MPS reused from run_mode={mps.get('run_mode')} "
                f"generated_at={mps.get('generated_at')} (D-02: no new evidence since that run)"
            )
        else:
            if reuse_mps_run is not None:
                mps_source = "scored_fallback"
                print(
                    "[final_report] reuse_mps_run was requested but the read-back was empty/malformed; "
                    "falling back to a fresh MPSAgent().score call"
                )
            else:
                mps_source = "scored"
            mps = MPSAgent().score(checked, catalog, company_name, spark, llm_endpoint, run_mode=run_mode)
            print(f"[final_report] MPS scoring: {mps.get('mps_status')} (run_mode={run_mode})")

        rendered = render_final_report(
            checked,
            catalog,
            company_name,
            narrative=narrative,
            mps=mps,
            prior_mps=prior_mps_runs,
            run_mode=run_mode,
        )

        status = "success"
        if (
            mps.get("mps_status") == "degraded"
            or er_narrative.get("synthesis_status") == "degraded"
            or fr_narrative.get("final_narrative_status") == "degraded"
        ):
            status = "degraded"

        return {
            "status": status,
            "html": rendered.get("html"),
            "pdf": rendered.get("pdf"),
            "pdf_degraded": bool(rendered.get("pdf_degraded", False)),
            "synthesis_status": er_narrative.get("synthesis_status"),
            "final_narrative_status": fr_narrative.get("final_narrative_status"),
            "mps_status": mps.get("mps_status"),
            "mps_source": mps_source,
            "error": None,
        }
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:  # noqa: BLE001 - build_final_report must never propagate (§0)
        error_msg = f"{type(exc).__name__}: {exc}"
        print(f"[final_report] build_final_report FAILED for {company_name}: {error_msg}")
        print(traceback.format_exc(limit=6))
        return {
            "status": "failed",
            "html": None,
            "pdf": None,
            "pdf_degraded": False,
            "synthesis_status": None,
            "final_narrative_status": None,
            "mps_status": None,
            "mps_source": None,
            "error": error_msg,
        }
