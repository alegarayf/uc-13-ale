"""Unit tests for the `file_whitelist` scoping added to download_upload.py /
ingestion_parser.py / run_ingestion_pipeline.py (CIM-first preview — plan §7
Día 2, Apéndice A.1). Verifies both the new scoping behavior and the
no-regression requirement (default = today's full-room behavior unchanged).
"""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Same pyspark/mlflow stub pattern as test_ingestion_parser_sync.py — avoids
# a hard dependency on a real Spark/mlflow install for this pure-logic test.
if "pyspark" not in sys.modules:
    _pyspark_mod = types.ModuleType("pyspark")
    _sql_mod = types.ModuleType("pyspark.sql")
    _types_mod = types.ModuleType("pyspark.sql.types")

    class _SparkSession:
        @staticmethod
        def getActiveSession():
            return None

    class _StubSparkType:
        def __init__(self, *args, **kwargs):
            pass

    _sql_mod.SparkSession = _SparkSession
    _sql_mod.Row = lambda **kwargs: SimpleNamespace(**kwargs)
    for _name in (
        "StructType", "StructField", "StringType", "IntegerType",
        "BooleanType", "ArrayType", "FloatType", "TimestampType",
    ):
        setattr(_types_mod, _name, _StubSparkType)
    _pyspark_mod.sql = _sql_mod
    sys.modules["pyspark"] = _pyspark_mod
    sys.modules["pyspark.sql"] = _sql_mod
    sys.modules["pyspark.sql.types"] = _types_mod

if "mlflow" not in sys.modules:
    _mlflow_mod = types.ModuleType("mlflow")
    _deployments_mod = types.ModuleType("mlflow.deployments")
    _deployments_mod.get_deploy_client = MagicMock(return_value=MagicMock())
    _mlflow_mod.deployments = _deployments_mod
    sys.modules["mlflow"] = _mlflow_mod
    sys.modules["mlflow.deployments"] = _deployments_mod

import download_upload as du  # noqa: E402
import ingestion_parser as ip  # noqa: E402
import run_ingestion_pipeline as rip  # noqa: E402


@dataclass
class _File:
    name: str


# ---------------------------------------------------------------------------
# download_upload.apply_file_whitelist
# ---------------------------------------------------------------------------

_FILES = [_File("cim.pdf"), _File("kpi.xlsx"), _File("contract.docx")]


def test_apply_file_whitelist_no_regression_when_empty():
    assert du.apply_file_whitelist(_FILES, "[]") == _FILES
    assert du.apply_file_whitelist(_FILES, "") == _FILES
    assert du.apply_file_whitelist(_FILES, None) == _FILES


def test_apply_file_whitelist_filters_to_named_files():
    result = du.apply_file_whitelist(_FILES, json.dumps(["cim.pdf"]))
    assert [f.name for f in result] == ["cim.pdf"]


def test_apply_file_whitelist_unknown_name_yields_empty():
    result = du.apply_file_whitelist(_FILES, json.dumps(["not_in_room.pdf"]))
    assert result == []


# ---------------------------------------------------------------------------
# ingestion_parser.build_file_whitelist_filter
# ---------------------------------------------------------------------------

def test_build_file_whitelist_filter_no_regression_when_empty():
    clause, label = ip.build_file_whitelist_filter("[]")
    assert clause == ""
    assert label == "no whitelist"


def test_build_file_whitelist_filter_builds_sql_in_clause():
    clause, label = ip.build_file_whitelist_filter(json.dumps(["2024 Elder Care - CIM_vF.pdf"]))
    assert clause == "AND filename IN ('2024 Elder Care - CIM_vF.pdf')"
    assert "1 file" in label


def test_build_file_whitelist_filter_escapes_single_quotes():
    clause, _ = ip.build_file_whitelist_filter(json.dumps(["Bob's CIM.pdf"]))
    assert "Bob''s CIM.pdf" in clause


# ---------------------------------------------------------------------------
# run_ingestion_pipeline — env mirroring + default no-regression
# ---------------------------------------------------------------------------

def test_run_ingestion_pipeline_default_mirrors_empty_whitelist(monkeypatch):
    monkeypatch.delenv("file_whitelist", raising=False)
    monkeypatch.setattr(rip, "_find_scripts_dir", lambda: str(_SCRIPTS_DIR))
    monkeypatch.setattr(rip, "_find_repo_root", lambda _scripts_dir: str(_REPO_ROOT / "databricks"))

    fake_module = SimpleNamespace(main=lambda: None)
    monkeypatch.setattr(rip, "_import_script", lambda *a, **k: fake_module)

    rip.run_ingestion_pipeline(company_name="Elder Care")
    assert json.loads(rip.os.environ["file_whitelist"]) == []


def test_run_ingestion_pipeline_mirrors_explicit_whitelist(monkeypatch):
    monkeypatch.setattr(rip, "_find_scripts_dir", lambda: str(_SCRIPTS_DIR))
    monkeypatch.setattr(rip, "_find_repo_root", lambda _scripts_dir: str(_REPO_ROOT / "databricks"))
    fake_module = SimpleNamespace(main=lambda: None)
    monkeypatch.setattr(rip, "_import_script", lambda *a, **k: fake_module)

    rip.run_ingestion_pipeline(
        company_name="GKF",
        file_whitelist=["Project Ajax CIM vF - Rallyday Partners.pdf"],
    )
    assert json.loads(rip.os.environ["file_whitelist"]) == [
        "Project Ajax CIM vF - Rallyday Partners.pdf"
    ]
