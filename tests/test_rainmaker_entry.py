"""Unit tests for agents/exec_summary/rainmaker_entry.py — the shared
executive-review builder both VDR branches (CIM-scoped and full-room) call.
Mocks BundleBuilder/validate_bundle/synthesize_rainmaker_narrative/
render_rainmaker so this runs offline, no cluster needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

# Same mlflow-stub-eviction guard as test_run_vdr_rainmaker.py — BundleBuilder
# does `import mlflow.pyfunc`, which breaks if a fake stub-module leaked in
# from another test file's narrow run.
_fake_mlflow = sys.modules.get("mlflow")
if _fake_mlflow is not None and not hasattr(_fake_mlflow, "__path__"):
    for _mod_name in [n for n in sys.modules if n == "mlflow" or n.startswith("mlflow.")]:
        del sys.modules[_mod_name]

from agents.exec_summary.rainmaker_entry import build_rainmaker_summary  # noqa: E402
from agents.exec_summary.validate import BundleValidationError  # noqa: E402


def _passthrough_verify_bundle_claims(monkeypatch, calls=None):
    """Most of this file's tests care about the build->validate->narrative->
    render chain, not the absence-check pass itself (that lives in
    test_absence_check.py) — patch it to a transparent passthrough so those
    tests aren't coupled to its internals or to a real (network) semantic
    search call."""

    def _verify(bundle, spark, catalog, company_name):
        if calls is not None:
            calls.append(("verify", bundle, spark, catalog, company_name))
        return bundle

    monkeypatch.setattr("agents.exec_summary.absence_check.verify_bundle_claims", _verify)


def test_calls_in_order_and_forwards_narrative_to_render(monkeypatch):
    fake_bundle = {"meta": {"company_name": "Elder Care"}}
    calls = []
    _passthrough_verify_bundle_claims(monkeypatch, calls)

    build_mock = MagicMock(return_value=fake_bundle)
    monkeypatch.setattr("agents.exec_summary.bundle_builder.BundleBuilder.build", build_mock)

    def _validate(bundle):
        calls.append(("validate", bundle))

    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", _validate)

    fake_narrative = {"synthesis_status": "success", "thesis": "worthy of pursuit"}

    def _synthesize(bundle, llm_endpoint, spark):
        calls.append(("narrative", bundle, llm_endpoint, spark))
        return fake_narrative

    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative", _synthesize
    )

    fake_mps = {"mps_status": "success", "run_mode": "cim_only"}

    def _score(self, bundle, catalog, company_name, spark, llm_endpoint, run_mode):
        calls.append(("mps", bundle, catalog, company_name, spark, llm_endpoint, run_mode))
        return fake_mps

    monkeypatch.setattr("agents.workstreams.mps_agent.MPSAgent.score", _score)

    def _render(bundle, catalog, company_name, narrative=None, mps=None):
        calls.append(("render", bundle, catalog, company_name, narrative, mps))
        return {"html": "/tmp/out.html", "pdf": "/tmp/out.pdf"}

    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", _render)

    spark = MagicMock()
    result = build_rainmaker_summary(
        "Elder Care", "uc13_preview", spark, "databricks-claude-sonnet-4-6", run_mode="cim_only"
    )

    # Call order: build -> validate -> verify_bundle_claims -> synthesize -> mps -> render.
    assert [c[0] for c in calls] == ["validate", "verify", "narrative", "mps", "render"]
    build_mock.assert_called_once_with("Elder Care", "uc13_preview", spark, "databricks-claude-sonnet-4-6")

    _, mps_bundle, mps_catalog, mps_company, mps_spark, mps_llm_endpoint, mps_run_mode = calls[3]
    assert mps_bundle == fake_bundle
    assert mps_catalog == "uc13_preview"
    assert mps_company == "Elder Care"
    assert mps_spark is spark
    assert mps_llm_endpoint == "databricks-claude-sonnet-4-6"
    assert mps_run_mode == "cim_only"

    _, render_bundle, render_catalog, render_company, render_narrative, render_mps = calls[4]
    assert render_bundle == fake_bundle
    assert render_catalog == "uc13_preview"
    assert render_company == "Elder Care"
    assert render_narrative == fake_narrative  # narrative forwarded to render_rainmaker
    assert render_mps == fake_mps  # mps forwarded to render_rainmaker

    assert result["html"] == "/tmp/out.html"
    assert result["pdf"] == "/tmp/out.pdf"
    assert result["synthesis_status"] == "success"
    assert result["mps_status"] == "success"


def test_verify_bundle_claims_output_feeds_narrative_and_render(monkeypatch):
    """The point of wiring in verify_bundle_claims (plan Part B, B2): its
    output — not BundleBuilder's raw output — is what the narrative LLM and
    the render layer actually see."""
    raw_bundle = {"meta": {}, "revenue_quality": {"concentration": ""}}
    checked_bundle = {"meta": {}, "revenue_quality": {"concentration": "[DATA ROOM MATERIAL NOT YET EXTRACTED] ..."}}

    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value=raw_bundle),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())

    verify_mock = MagicMock(return_value=checked_bundle)
    monkeypatch.setattr("agents.exec_summary.absence_check.verify_bundle_claims", verify_mock)

    seen = {}

    def _synthesize(bundle, llm_endpoint, spark):
        seen["narrative_bundle"] = bundle
        return {"synthesis_status": "success"}

    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative", _synthesize
    )

    def _score(self, bundle, catalog, company_name, spark, llm_endpoint, run_mode):
        seen["mps_bundle"] = bundle
        return {"mps_status": "success"}

    monkeypatch.setattr("agents.workstreams.mps_agent.MPSAgent.score", _score)

    def _render(bundle, catalog, company_name, narrative=None, mps=None):
        seen["render_bundle"] = bundle
        return {"html": "/tmp/out.html"}

    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", _render)

    spark = MagicMock()
    build_rainmaker_summary(
        "Elder Care", "uc13_preview", spark, "databricks-claude-sonnet-4-6", run_mode="full_vdr_no_cim"
    )

    verify_mock.assert_called_once_with(raw_bundle, spark, "uc13_preview", "Elder Care")
    assert seen["narrative_bundle"] == checked_bundle
    assert seen["mps_bundle"] == checked_bundle
    assert seen["render_bundle"] == checked_bundle


def test_catalog_passed_through_unchanged(monkeypatch):
    """Catalog-agnostic by construction — both VDR branches pass their own
    catalog straight through to every stage."""
    _passthrough_verify_bundle_claims(monkeypatch)
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value={"meta": {}}),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative",
        MagicMock(return_value={"synthesis_status": "degraded"}),
    )
    monkeypatch.setattr(
        "agents.workstreams.mps_agent.MPSAgent.score",
        MagicMock(return_value={"mps_status": "degraded"}),
    )
    render_mock = MagicMock(return_value={"html": "/tmp/out.html"})
    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", render_mock)

    build_rainmaker_summary(
        "GKF", "some_other_catalog", MagicMock(), "databricks-claude-sonnet-4-6", run_mode="cim_only"
    )

    args, _kwargs = render_mock.call_args
    assert args[1] == "some_other_catalog"


def test_validate_bundle_failure_propagates(monkeypatch):
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value={"meta": {}}),
    )

    def _raise(_bundle):
        raise BundleValidationError("missing required field")

    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", _raise)

    verify_mock = MagicMock(side_effect=AssertionError("must not verify after a validation failure"))
    monkeypatch.setattr("agents.exec_summary.absence_check.verify_bundle_claims", verify_mock)
    narrative_mock = MagicMock(side_effect=AssertionError("must not synthesize after a validation failure"))
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative", narrative_mock
    )
    mps_mock = MagicMock(side_effect=AssertionError("must not score after a validation failure"))
    monkeypatch.setattr("agents.workstreams.mps_agent.MPSAgent.score", mps_mock)
    render_mock = MagicMock(side_effect=AssertionError("must not render after a validation failure"))
    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", render_mock)

    with pytest.raises(BundleValidationError, match="missing required field"):
        build_rainmaker_summary(
            "Elder Care", "uc13_preview", MagicMock(), "databricks-claude-sonnet-4-6", run_mode="cim_only"
        )

    verify_mock.assert_not_called()
    narrative_mock.assert_not_called()
    mps_mock.assert_not_called()
    render_mock.assert_not_called()


def test_mps_failure_degrades_but_executive_review_still_renders(monkeypatch):
    """§0's non-negotiable contract, end-to-end: MPSAgent never raises, and
    a failed MPS must not stop the executive review from rendering. Uses the
    real ``MPSAgent.score`` (not a mock) and breaks the one thing it calls
    out to an LLM for, so this exercises the agent's own degradation path
    rather than asserting a canned mock."""
    _passthrough_verify_bundle_claims(monkeypatch)
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value={"meta": {"company_name": "Elder Care"}}),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative",
        MagicMock(return_value={"synthesis_status": "success"}),
    )
    monkeypatch.setattr(
        "agents.shared.agent_base.WorkstreamAgent._call_llm",
        MagicMock(side_effect=RuntimeError("serving endpoint timed out")),
    )

    seen = {}

    def _render(bundle, catalog, company_name, narrative=None, mps=None):
        seen["mps"] = mps
        return {"html": "/tmp/out.html", "pdf": "/tmp/out.pdf"}

    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", _render)

    result = build_rainmaker_summary(
        "Elder Care", "uc13_preview", MagicMock(), "databricks-claude-sonnet-4-6", run_mode="cim_only"
    )

    assert seen["mps"]["mps_status"] == "degraded"
    assert result["mps_status"] == "degraded"
    assert result["html"] == "/tmp/out.html"
    assert result["pdf"] == "/tmp/out.pdf"
