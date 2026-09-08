"""Unit tests for agents/exec_summary/final_report_entry.py — the bridge
that turns a completed agent run into the final report. Mocks
BundleBuilder/validate_bundle/synthesize_rainmaker_narrative/
render_final_report/MPSAgent.score so this runs offline, no cluster needed.
Modelled on tests/test_rainmaker_entry.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

# Same mlflow-stub-eviction guard as test_run_vdr_rainmaker.py / test_rainmaker_entry.py.
_fake_mlflow = sys.modules.get("mlflow")
if _fake_mlflow is not None and not hasattr(_fake_mlflow, "__path__"):
    for _mod_name in [n for n in sys.modules if n == "mlflow" or n.startswith("mlflow.")]:
        del sys.modules[_mod_name]

from agents.exec_summary.final_report_entry import (  # noqa: E402
    _load_forecast,
    _load_prior_mps_runs,
    build_final_report,
)


def _passthrough_verify_bundle_claims(monkeypatch, calls=None):
    def _verify(bundle, spark, catalog, company_name):
        if calls is not None:
            calls.append(("verify", bundle, spark, catalog, company_name))
        return bundle

    monkeypatch.setattr("agents.exec_summary.absence_check.verify_bundle_claims", _verify)


def _no_forecast(monkeypatch):
    """Most tests here care about the build->validate->narrative->mps->render
    chain, not the D-03 forecast read-back (covered separately below) —
    patch it to a no-op so those tests aren't coupled to a Spark mock."""
    monkeypatch.setattr(
        "agents.exec_summary.final_report_entry._load_forecast", MagicMock(return_value={})
    )


def _no_final_narrative(monkeypatch, calls=None):
    """T11's final_report_narrative call is real code, not a stub — most
    tests here care about the build->validate->narrative->mps->render chain
    and would otherwise hit the LLM gateway for real. Patch it to a no-op
    success so those tests stay hermetic."""

    def _synthesize(bundle, llm_endpoint, spark):
        if calls is not None:
            calls.append(("final_narrative", bundle, llm_endpoint, spark))
        return {"final_narrative_status": "success"}

    monkeypatch.setattr(
        "agents.exec_summary.final_report_narrative.synthesize_final_report_narrative", _synthesize
    )


# =========================================================================
# The happy path — call order, run_mode threading, prior_mps_runs ordering
# =========================================================================


def test_calls_in_order_and_threads_run_mode_to_mps_and_render(monkeypatch):
    fake_bundle = {"meta": {"company_name": "Elder Care"}, "financials": {}}
    calls = []
    _passthrough_verify_bundle_claims(monkeypatch, calls)
    _no_forecast(monkeypatch)

    build_mock = MagicMock(return_value=fake_bundle)
    monkeypatch.setattr("agents.exec_summary.bundle_builder.BundleBuilder.build", build_mock)

    def _validate(bundle):
        calls.append(("validate", bundle))

    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", _validate)

    fake_er_narrative = {"synthesis_status": "success", "business_model": ["b1"]}
    fake_fr_narrative = {"final_narrative_status": "success", "recommendation": {"verdict": "Proceed"}}

    def _synthesize_er(bundle, llm_endpoint, spark):
        calls.append(("er_narrative", bundle, llm_endpoint, spark))
        return fake_er_narrative

    def _synthesize_fr(bundle, llm_endpoint, spark):
        calls.append(("fr_narrative", bundle, llm_endpoint, spark))
        return fake_fr_narrative

    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative", _synthesize_er
    )
    monkeypatch.setattr(
        "agents.exec_summary.final_report_narrative.synthesize_final_report_narrative", _synthesize_fr
    )

    fake_mps = {"mps_status": "success", "run_mode": "full_vdr_after_cim"}

    def _score(self, bundle, catalog, company_name, spark, llm_endpoint, run_mode):
        calls.append(("mps", bundle, catalog, company_name, spark, llm_endpoint, run_mode))
        return fake_mps

    monkeypatch.setattr("agents.workstreams.mps_agent.MPSAgent.score", _score)

    def _render(bundle, catalog, company_name, narrative=None, mps=None, prior_mps=None, run_mode=None):
        calls.append(("render", bundle, catalog, company_name, narrative, mps, prior_mps, run_mode))
        return {"html": "/tmp/out.html", "pdf": "/tmp/out.pdf"}

    monkeypatch.setattr("agents.exec_summary.renderers.render_final_report", _render)

    spark = MagicMock()
    prior_runs = [{"run_mode": "cim_only", "generated_at": "2026-01-01"}]
    result = build_final_report(
        "Elder Care",
        "uc13_preview",
        spark,
        "databricks-claude-sonnet-4-6",
        run_mode="full_vdr_after_cim",
        prior_mps_runs=prior_runs,
    )

    assert [c[0] for c in calls] == ["validate", "verify", "er_narrative", "fr_narrative", "mps", "render"]
    build_mock.assert_called_once_with("Elder Care", "uc13_preview", spark, "databricks-claude-sonnet-4-6")

    _, mps_bundle, mps_catalog, mps_company, mps_spark, mps_llm_endpoint, mps_run_mode = calls[4]
    assert mps_bundle == fake_bundle
    assert mps_catalog == "uc13_preview"
    assert mps_company == "Elder Care"
    assert mps_spark is spark
    assert mps_llm_endpoint == "databricks-claude-sonnet-4-6"
    assert mps_run_mode == "full_vdr_after_cim"  # run_mode reached MPSAgent().score

    (
        _,
        render_bundle,
        render_catalog,
        render_company,
        render_narrative,
        render_mps,
        render_prior_mps,
        render_run_mode,
    ) = calls[5]
    assert render_bundle == fake_bundle
    assert render_catalog == "uc13_preview"
    assert render_company == "Elder Care"
    # The merge is {**er, **fr}: fr's key wins on the one overlapping key
    # (`recommendation`), er's other keys pass through untouched.
    assert render_narrative == {**fake_er_narrative, **fake_fr_narrative}
    assert render_narrative["recommendation"] == {"verdict": "Proceed"}
    assert render_narrative["business_model"] == ["b1"]
    assert render_mps == fake_mps  # the CURRENT run reaches render_final_report as `mps`
    assert render_prior_mps == prior_runs  # prior_mps_runs reaches render_final_report as `prior_mps`
    assert render_run_mode == "full_vdr_after_cim"  # run_mode reached render_final_report too

    assert result["status"] == "success"
    assert result["html"] == "/tmp/out.html"
    assert result["pdf"] == "/tmp/out.pdf"
    assert result["synthesis_status"] == "success"
    assert result["final_narrative_status"] == "success"
    assert result["mps_status"] == "success"
    assert result["mps_source"] == "scored"


# =========================================================================
# The three failure paths — never raises, status="failed"
# =========================================================================


def test_raising_bundle_builder_produces_failed_status_no_exception_escapes(monkeypatch):
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(side_effect=RuntimeError("boom")),
    )

    result = build_final_report(
        "Elder Care", "uc13_preview", MagicMock(), "databricks-claude-sonnet-4-6", run_mode="cim_only"
    )

    assert result["status"] == "failed"
    assert result["html"] is None
    assert result["pdf"] is None
    assert "boom" in result["error"]


def test_raising_narrative_produces_failed_status_no_exception_escapes(monkeypatch):
    _passthrough_verify_bundle_claims(monkeypatch)
    _no_forecast(monkeypatch)
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value={"meta": {}, "financials": {}}),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative",
        MagicMock(side_effect=RuntimeError("narrative exploded")),
    )
    mps_mock = MagicMock(side_effect=AssertionError("must not score after a narrative failure"))
    monkeypatch.setattr("agents.workstreams.mps_agent.MPSAgent.score", mps_mock)
    render_mock = MagicMock(side_effect=AssertionError("must not render after a narrative failure"))
    monkeypatch.setattr("agents.exec_summary.renderers.render_final_report", render_mock)

    result = build_final_report(
        "Elder Care", "uc13_preview", MagicMock(), "databricks-claude-sonnet-4-6", run_mode="cim_only"
    )

    assert result["status"] == "failed"
    assert "narrative exploded" in result["error"]
    mps_mock.assert_not_called()
    render_mock.assert_not_called()


def test_raising_renderer_produces_failed_status_no_exception_escapes(monkeypatch):
    _passthrough_verify_bundle_claims(monkeypatch)
    _no_forecast(monkeypatch)
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value={"meta": {}, "financials": {}}),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative",
        MagicMock(return_value={"synthesis_status": "success"}),
    )
    _no_final_narrative(monkeypatch)
    monkeypatch.setattr(
        "agents.workstreams.mps_agent.MPSAgent.score",
        MagicMock(return_value={"mps_status": "success", "run_mode": "cim_only"}),
    )
    monkeypatch.setattr(
        "agents.exec_summary.renderers.render_final_report",
        MagicMock(side_effect=RuntimeError("render exploded")),
    )

    result = build_final_report(
        "Elder Care", "uc13_preview", MagicMock(), "databricks-claude-sonnet-4-6", run_mode="cim_only"
    )

    assert result["status"] == "failed"
    assert "render exploded" in result["error"]


# =========================================================================
# _load_prior_mps_runs — read-back from {catalog}.analysis.mps_score
# =========================================================================


def test_load_prior_mps_runs_returns_empty_list_on_raising_spark():
    spark = MagicMock()
    spark.sql.side_effect = RuntimeError("table not found")
    assert _load_prior_mps_runs(spark, "uc13_preview", "Elder Care") == []


def test_load_prior_mps_runs_returns_empty_list_on_empty_result():
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = []
    assert _load_prior_mps_runs(spark, "uc13_preview", "Elder Care") == []


def test_load_prior_mps_runs_returns_empty_list_on_malformed_categories_json():
    row = MagicMock()
    row.asDict.return_value = {
        "run_mode": "cim_only",
        "generated_at": "2026-01-01T00:00:00",
        "categories_json": "{not valid json",
        "threshold": 3.5,
        "mps_status": "success",
        "total": 4.0,
        "verdict": "Proceed",
    }
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [row]
    assert _load_prior_mps_runs(spark, "uc13_preview", "Elder Care") == []


def test_load_prior_mps_runs_returns_runs_oldest_first():
    def _row(run_mode, generated_at):
        row = MagicMock()
        row.asDict.return_value = {
            "run_mode": run_mode,
            "generated_at": generated_at,
            "categories_json": json.dumps([{"category": "x", "score": 4}]),
            "threshold": 3.5,
            "mps_status": "success",
            "total": 4.0,
            "verdict": "Proceed",
        }
        return row

    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        _row("full_vdr_no_cim", "2026-02-01T00:00:00"),
        _row("cim_only", "2026-01-01T00:00:00"),
    ]

    runs = _load_prior_mps_runs(spark, "uc13_preview", "Elder Care", run_modes=("cim_only", "full_vdr_no_cim"))

    assert [r["run_mode"] for r in runs] == ["cim_only", "full_vdr_no_cim"]
    assert runs[0]["generated_at"] < runs[1]["generated_at"]


# =========================================================================
# D-03 — _load_forecast reads {catalog}.analysis.forecast
# =========================================================================


def _forecast_row(**overrides):
    row = MagicMock()
    payload = {
        "revenue_build_comparison_json": json.dumps(
            [{"period": "2026", "forecast_revenue": "12.0"}]
        ),
        "forecast_assumptions_json": json.dumps(
            [
                {
                    "assumption_type": "revenue_growth_rate",
                    "description": "22% YoY growth",
                    "stated_value": "22% YoY",
                    "credibility_rating": "Plausible",
                }
            ]
        ),
        "management_validation_items_json": json.dumps(
            [
                {
                    "item": "Substantiate the revenue growth rate assumption",
                    "priority": "medium",
                    "related_assumption": "revenue_growth_rate",
                }
            ]
        ),
    }
    payload.update(overrides)
    row.asDict.return_value = payload
    return row


def test_load_forecast_maps_agent_columns_and_never_substitutes_margin():
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [_forecast_row()]

    result = _load_forecast(spark, "uc13_preview", "Elder Care")

    assert result["forecast_rows"] == [{"year": "2026", "revenue": "12.0"}]
    assert "ebitda_margin_pct" not in result["forecast_rows"][0]

    assumption = result["forecast_assumptions"][0]
    assert assumption["assumption"] == "22% YoY growth"
    assert assumption["support"] == "Plausible"
    assert assumption["test"] == "Substantiate the revenue growth rate assumption"


def test_load_forecast_returns_empty_dict_on_raising_spark():
    spark = MagicMock()
    spark.sql.side_effect = RuntimeError("table not found")
    assert _load_forecast(spark, "uc13_preview", "Elder Care") == {}


def test_load_forecast_returns_empty_dict_on_empty_table():
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = []
    assert _load_forecast(spark, "uc13_preview", "Elder Care") == {}


def test_load_forecast_returns_empty_dict_on_malformed_json():
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        _forecast_row(revenue_build_comparison_json="{not valid json")
    ]
    assert _load_forecast(spark, "uc13_preview", "Elder Care") == {}


def test_forecast_reaches_narrative_and_render(monkeypatch):
    """The D-03 merge happens before both the narrative call and the render
    call, on a copied financials dict — BundleBuilder's own bundle is never
    mutated."""
    raw_bundle = {"meta": {}, "financials": {"table_rows": [{"year": "2025A"}]}}
    calls = {}
    _passthrough_verify_bundle_claims(monkeypatch)
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value=raw_bundle),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())
    monkeypatch.setattr(
        "agents.exec_summary.final_report_entry._load_forecast",
        MagicMock(return_value={"forecast_rows": [{"year": "2026P", "revenue": "12"}]}),
    )

    def _synthesize(bundle, llm_endpoint, spark):
        calls["narrative_bundle"] = bundle
        return {"synthesis_status": "success"}

    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative", _synthesize
    )
    _no_final_narrative(monkeypatch)
    monkeypatch.setattr(
        "agents.workstreams.mps_agent.MPSAgent.score",
        MagicMock(return_value={"mps_status": "success", "run_mode": "cim_only"}),
    )

    def _render(bundle, catalog, company_name, narrative=None, mps=None, prior_mps=None, run_mode=None):
        calls["render_bundle"] = bundle
        return {"html": "/tmp/out.html"}

    monkeypatch.setattr("agents.exec_summary.renderers.render_final_report", _render)

    build_final_report(
        "Elder Care", "uc13_preview", MagicMock(), "databricks-claude-sonnet-4-6", run_mode="cim_only"
    )

    assert calls["narrative_bundle"]["financials"]["forecast_rows"] == [{"year": "2026P", "revenue": "12"}]
    assert calls["render_bundle"]["financials"]["forecast_rows"] == [{"year": "2026P", "revenue": "12"}]
    # The original bundle BundleBuilder returned is untouched.
    assert "forecast_rows" not in raw_bundle["financials"]


# =========================================================================
# D-02 — reuse_mps_run skips MPSAgent().score entirely
# =========================================================================


def test_reuse_mps_run_skips_scoring_and_reaches_render_as_mps(monkeypatch):
    _passthrough_verify_bundle_claims(monkeypatch)
    _no_forecast(monkeypatch)
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value={"meta": {}, "financials": {}}),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative",
        MagicMock(return_value={"synthesis_status": "success"}),
    )
    _no_final_narrative(monkeypatch)

    score_mock = MagicMock(side_effect=AssertionError("MPSAgent.score must not be called on reuse"))
    monkeypatch.setattr("agents.workstreams.mps_agent.MPSAgent.score", score_mock)

    reused_run = {"mps_status": "success", "run_mode": "full_vdr_no_cim", "generated_at": "2026-01-01"}
    seen = {}

    def _render(bundle, catalog, company_name, narrative=None, mps=None, prior_mps=None, run_mode=None):
        seen["mps"] = mps
        return {"html": "/tmp/out.html"}

    monkeypatch.setattr("agents.exec_summary.renderers.render_final_report", _render)

    result = build_final_report(
        "Elder Care",
        "uc13_preview",
        MagicMock(),
        "databricks-claude-sonnet-4-6",
        run_mode="full_vdr_no_cim",
        reuse_mps_run=reused_run,
    )

    score_mock.assert_not_called()
    assert seen["mps"] == reused_run
    assert result["mps_source"] == "reused"
    assert result["mps_status"] == "success"


def test_reuse_mps_run_fallback_scores_when_readback_was_empty(monkeypatch):
    """D-02 fallback: reuse was requested (Branch B) but the read-back found
    nothing — a fresh MPSAgent().score call must still happen so the page
    carries a number, reported as mps_source="scored_fallback"."""
    _passthrough_verify_bundle_claims(monkeypatch)
    _no_forecast(monkeypatch)
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value={"meta": {}, "financials": {}}),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative",
        MagicMock(return_value={"synthesis_status": "success"}),
    )
    _no_final_narrative(monkeypatch)

    fresh_run = {"mps_status": "success", "run_mode": "full_vdr_no_cim"}
    score_mock = MagicMock(return_value=fresh_run)
    monkeypatch.setattr("agents.workstreams.mps_agent.MPSAgent.score", score_mock)
    monkeypatch.setattr(
        "agents.exec_summary.renderers.render_final_report",
        MagicMock(return_value={"html": "/tmp/out.html"}),
    )

    result = build_final_report(
        "Elder Care",
        "uc13_preview",
        MagicMock(),
        "databricks-claude-sonnet-4-6",
        run_mode="full_vdr_no_cim",
        reuse_mps_run={},  # read-back yielded nothing — malformed/empty, not None
    )

    score_mock.assert_called_once()
    assert result["mps_source"] == "scored_fallback"
    assert result["mps_status"] == "success"
