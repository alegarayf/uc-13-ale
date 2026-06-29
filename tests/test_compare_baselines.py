"""Tests for .dev/legal_agent/_compare_baselines.py path helpers (T4)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_COMPARE_PATH = _ROOT / ".dev" / "legal_agent" / "_compare_baselines.py"


def _load_compare():
    spec = importlib.util.spec_from_file_location("compare_baselines", _COMPARE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_volume_paths_default_catalog():
    mod = _load_compare()
    legacy, normative = mod.volume_paths("uc13_ale", "Elder Care")
    assert legacy == "/Volumes/uc13_ale/analysis/reports/Elder_Care/legal_contracts_report.yaml"
    assert normative == "/Volumes/uc13_ale/analysis/reports/Elder_Care/legal_report.yaml"


def test_volume_paths_custom_catalog_and_slug():
    mod = _load_compare()
    legacy, normative = mod.volume_paths("uc13", "Acme Corp")
    assert legacy.startswith("/Volumes/uc13/analysis/reports/Acme_Corp/")
    assert normative.endswith("legal_report.yaml")


def test_normative_outline_keys_complete():
    mod = _load_compare()
    doc = {key: {} for key in mod.NORMATIVE_OUTLINE_KEYS}
    doc["report"] = {"agent": "legal_contracts"}
    check = mod.outline_check(doc)
    assert check["outline_complete"] is True
    assert check["missing_keys"] == []


def test_normative_outline_missing_section():
    mod = _load_compare()
    doc = {"report": {}, "confidence": "high"}
    check = mod.outline_check(doc)
    assert check["outline_complete"] is False
    assert "Insurance" in check["missing_keys"]
