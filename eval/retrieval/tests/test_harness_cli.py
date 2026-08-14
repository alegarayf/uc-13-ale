"""Harness CLI gold-path derivation tests — M4 T3."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _path in (_REPO_ROOT / "databricks", _REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from eval.retrieval.harness_cli import main


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
