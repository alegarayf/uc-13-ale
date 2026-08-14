"""Harness CLI gold-path derivation tests — M4 T3."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _path in (_REPO_ROOT / "databricks", _REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from eval.retrieval.harness_cli import main


def _run_main(argv: list[str]) -> tuple[int, str]:
    buffer = StringIO()
    with patch("sys.stdout", buffer):
        exit_code = main(argv)
    return exit_code, buffer.getvalue().strip()


@patch("eval.retrieval.harness_cli.EvalHarness")
@patch("eval.retrieval.harness_cli._build_store")
def test_run_derives_gold_path_from_company_name(
    mock_build_store,
    mock_eval_harness,
):
    mock_harness = MagicMock()
    mock_eval_harness.return_value = mock_harness
    mock_harness.run.return_value = MagicMock(manifest=MagicMock(run_id="run_001"))
    mock_store = MagicMock()
    mock_build_store.return_value = mock_store

    exit_code = main(
        [
            "run",
            "--store-backend",
            "sqlite",
            "--run-type",
            "baseline",
            "--company-name",
            "Elder Care",
            "--catalog",
            "uc13_ale",
        ]
    )

    assert exit_code == 0
    mock_eval_harness.assert_called_once()
    harness_kwargs = mock_eval_harness.call_args.kwargs
    assert harness_kwargs["company_slug"] == "elder_care"
    assert "gold_path" not in harness_kwargs
    mock_harness.run.assert_called_once()
    run_kwargs = mock_harness.run.call_args.kwargs
    assert run_kwargs["company_name"] == "Elder Care"


@patch("eval.retrieval.harness_cli.EvalHarness")
@patch("eval.retrieval.harness_cli._build_store")
def test_run_summary_line_names_company_slug_and_catalog(
    mock_build_store,
    mock_eval_harness,
):
    mock_harness = MagicMock()
    mock_eval_harness.return_value = mock_harness
    mock_harness.run.return_value = MagicMock(manifest=MagicMock(run_id="baseline_abc"))
    mock_build_store.return_value = MagicMock()

    exit_code, summary = _run_main(
        [
            "run",
            "--store-backend",
            "sqlite",
            "--run-type",
            "baseline",
            "--company-name",
            "Clearsulting",
            "--catalog",
            "uc13_ale",
        ]
    )

    assert exit_code == 0
    assert "run_id=baseline_abc" in summary
    assert "company=clearsulting" in summary
    assert "catalog=uc13_ale" in summary


@patch("eval.retrieval.harness_cli.EvalHarness")
@patch("eval.retrieval.harness_cli._build_store")
def test_run_explicit_gold_path_skips_company_slug_derivation(
    mock_build_store,
    mock_eval_harness,
):
    custom_gold = Path("/tmp/custom_gold.yaml")
    mock_harness = MagicMock()
    mock_eval_harness.return_value = mock_harness
    mock_harness.run.return_value = MagicMock(manifest=MagicMock(run_id="run_002"))
    mock_build_store.return_value = MagicMock()

    exit_code = main(
        [
            "run",
            "--store-backend",
            "sqlite",
            "--run-type",
            "baseline",
            "--company-name",
            "Elder Care",
            "--catalog",
            "uc13_ale",
            "--gold-path",
            str(custom_gold),
        ]
    )

    assert exit_code == 0
    harness_kwargs = mock_eval_harness.call_args.kwargs
    assert harness_kwargs["gold_path"] == custom_gold
    assert "company_slug" not in harness_kwargs


@patch("eval.retrieval.harness_cli.EvalHarness")
@patch("eval.retrieval.harness_cli._build_store")
def test_run_unnormalizable_company_name_fails_before_harness_run(
    mock_build_store,
    mock_eval_harness,
):
    mock_harness = MagicMock()
    mock_eval_harness.return_value = mock_harness

    exit_code, _ = _run_main(
        [
            "run",
            "--store-backend",
            "sqlite",
            "--run-type",
            "baseline",
            "--company-name",
            "!!!",
            "--catalog",
            "uc13_ale",
            "--gold-path",
            "/tmp/custom_gold.yaml",
        ]
    )

    assert exit_code == 1
    mock_build_store.assert_not_called()
    mock_harness.run.assert_not_called()


@patch("eval.retrieval.harness_cli.EvalHarness")
@patch("eval.retrieval.harness_cli._build_store")
def test_validate_baseline_summary_line_names_company_slug_and_catalog(
    mock_build_store,
    mock_eval_harness,
):
    mock_store = MagicMock()
    mock_store.get_run.return_value = MagicMock(
        manifest=MagicMock(company_name="Elder Care", gated_intents=["fta.opex.q1"])
    )
    mock_build_store.return_value = mock_store
    mock_harness = MagicMock()
    mock_eval_harness.return_value = mock_harness

    exit_code, summary = _run_main(
        [
            "validate-baseline",
            "--store-backend",
            "sqlite",
            "--baseline-ref-run-id",
            "baseline_old",
            "--current-run-id",
            "enh_new",
            "--catalog",
            "uc13_ale",
        ]
    )

    assert exit_code == 0
    assert "baseline_ref validation passed" in summary
    assert "company=elder_care" in summary
    assert "catalog=uc13_ale" in summary
