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


def test_calls_in_order_and_forwards_narrative_to_render(monkeypatch):
    fake_bundle = {"meta": {"company_name": "Elder Care"}}
    calls = []

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

    def _render(bundle, catalog, company_name, narrative=None):
        calls.append(("render", bundle, catalog, company_name, narrative))
        return {"html": "/tmp/out.html", "pdf": "/tmp/out.pdf"}

    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", _render)

    spark = MagicMock()
    result = build_rainmaker_summary("Elder Care", "uc13_preview", spark, "databricks-claude-sonnet-4-6")

    # Call order: build -> validate -> synthesize -> render.
    assert [c[0] for c in calls] == ["validate", "narrative", "render"]
    build_mock.assert_called_once_with("Elder Care", "uc13_preview", spark, "databricks-claude-sonnet-4-6")

    _, render_bundle, render_catalog, render_company, render_narrative = calls[2]
    assert render_bundle is fake_bundle
    assert render_catalog == "uc13_preview"
    assert render_company == "Elder Care"
    assert render_narrative == fake_narrative  # narrative forwarded to render_rainmaker

    assert result["html"] == "/tmp/out.html"
    assert result["pdf"] == "/tmp/out.pdf"
    assert result["synthesis_status"] == "success"


def test_catalog_passed_through_unchanged(monkeypatch):
    """Catalog-agnostic by construction — both VDR branches pass their own
    catalog straight through to every stage."""
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build",
        MagicMock(return_value={"meta": {}}),
    )
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", MagicMock())
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative",
        MagicMock(return_value={"synthesis_status": "degraded"}),
    )
    render_mock = MagicMock(return_value={"html": "/tmp/out.html"})
    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", render_mock)

    build_rainmaker_summary("GKF", "some_other_catalog", MagicMock(), "databricks-claude-sonnet-4-6")

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

    narrative_mock = MagicMock(side_effect=AssertionError("must not synthesize after a validation failure"))
    monkeypatch.setattr(
        "agents.exec_summary.rainmaker_narrative.synthesize_rainmaker_narrative", narrative_mock
    )
    render_mock = MagicMock(side_effect=AssertionError("must not render after a validation failure"))
    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", render_mock)

    with pytest.raises(BundleValidationError, match="missing required field"):
        build_rainmaker_summary("Elder Care", "uc13_preview", MagicMock(), "databricks-claude-sonnet-4-6")

    narrative_mock.assert_not_called()
    render_mock.assert_not_called()
