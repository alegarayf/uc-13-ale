"""parse_file dispatch, chunk-cap, bracket-PDF, and embed-batching tests (M4 / T1)."""

from __future__ import annotations

import builtins
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Spark-free stub (mirrors tests/test_ingestion_parser_sync.py) for parse_pdf internals.
class _StubSparkType:
    def __init__(self, *args, **kwargs):
        pass


def _ensure_pyspark_stub() -> None:
    if "pyspark" not in sys.modules:
        _pyspark_mod = types.ModuleType("pyspark")
        _sql_mod = types.ModuleType("pyspark.sql")
        _pyspark_mod.sql = _sql_mod
        sys.modules["pyspark"] = _pyspark_mod
        sys.modules["pyspark.sql"] = _sql_mod
    else:
        _sql_mod = sys.modules["pyspark.sql"]

    if "pyspark.sql.types" not in sys.modules:
        _types_mod = types.ModuleType("pyspark.sql.types")
        sys.modules["pyspark.sql.types"] = _types_mod
        _sql_mod.types = _types_mod
    else:
        _types_mod = sys.modules["pyspark.sql.types"]

    class _ColExpr:
        def alias(self, _name: str):
            return self

    if "pyspark.sql.functions" not in sys.modules:
        _functions_mod = types.ModuleType("pyspark.sql.functions")
        sys.modules["pyspark.sql.functions"] = _functions_mod
    else:
        _functions_mod = sys.modules["pyspark.sql.functions"]

    _functions_mod.expr = lambda sql: _ColExpr()
    _functions_mod.to_json = lambda col: _ColExpr()

    class _SparkSession:
        @staticmethod
        def getActiveSession():
            return None

    _sql_mod.SparkSession = _SparkSession
    _sql_mod.Row = lambda **kwargs: SimpleNamespace(**kwargs)
    for _name in (
        "StructType",
        "StructField",
        "StringType",
        "IntegerType",
        "BooleanType",
        "ArrayType",
        "FloatType",
        "TimestampType",
        "BinaryType",
        "LongType",
    ):
        if not hasattr(_types_mod, _name):
            setattr(_types_mod, _name, _StubSparkType)


_ensure_pyspark_stub()

import ingestion_parser as ip  # noqa: E402

_DOC_ID = "a" * 32
_LONG_TEXT = "x" * 200


def _stub_chunk(
    file_name: str,
    file_type: str,
    *,
    chunk_index: int = 0,
) -> ip.Chunk:
    return ip.Chunk(
        chunk_id=f"chunk-{chunk_index}",
        doc_id=_DOC_ID,
        file_name=file_name,
        file_type=file_type,
        relative_path=file_name,
        chunk_index=chunk_index,
        chunk_text=_LONG_TEXT,
    )


def _pdf_parse_result() -> dict:
    return {
        "document": {
            "elements": [
                {
                    "type": "text",
                    "content": "A" * 200,
                    "bbox": [{"page_id": 0}],
                }
            ]
        }
    }


def _mock_spark_for_pdf(parsed: dict) -> MagicMock:
    spark = MagicMock()
    row = {"parsed": json.dumps(parsed)}
    spark.createDataFrame.return_value.select.return_value.collect.return_value = [row]
    return spark


@pytest.mark.parametrize(
    ("file_name", "parser_attr"),
    [
        ("report.pdf", "parse_pdf"),
        ("model.xlsx", "parse_excel"),
        ("legacy.xls", "parse_excel"),
        ("macro.xlsm", "parse_excel"),
        ("memo.docx", "parse_word"),
        ("legacy.doc", "parse_word"),
        ("export.csv", "parse_csv"),
    ],
)
def test_parse_file_dispatches_to_extension_parser(
    file_name: str,
    parser_attr: str,
) -> None:
    stub = [_stub_chunk(file_name, Path(file_name).suffix.lstrip("."))]
    fake_path = f"/tmp/{file_name}"
    captured: dict[str, str] = {}

    if parser_attr == "parse_pdf":

        def _capture_pdf(
            file_path: str, doc_id: str, fname: str, spark, **kwargs
        ) -> list[ip.Chunk]:
            captured["file_path"] = file_path
            captured["doc_id"] = doc_id
            captured["file_name"] = fname
            captured["spark"] = spark
            return stub

        side_effect = _capture_pdf
    else:

        def _capture(file_path: str, doc_id: str, fname: str, *args, **kwargs) -> list[ip.Chunk]:
            captured["file_path"] = file_path
            captured["doc_id"] = doc_id
            captured["file_name"] = fname
            return stub

        side_effect = _capture

    with patch(f"ingestion_parser.{parser_attr}", side_effect=side_effect) as mock_parser:
        spark = MagicMock()
        result = ip.parse_file(fake_path, _DOC_ID, spark)

    mock_parser.assert_called_once()
    assert captured["file_path"] == fake_path
    assert captured["doc_id"] == _DOC_ID
    assert captured["file_name"] == file_name
    assert result == stub


def test_parse_file_truncates_at_max_chunks_per_file(capsys: pytest.CaptureFixture[str]) -> None:
    file_name = "huge.csv"
    over_cap = ip.MAX_CHUNKS_PER_FILE + 7
    many = [
        _stub_chunk(file_name, "csv", chunk_index=i)
        for i in range(over_cap)
    ]

    with patch("ingestion_parser.parse_csv", return_value=many):
        result = ip.parse_file(f"/tmp/{file_name}", _DOC_ID, MagicMock())

    assert len(result) == ip.MAX_CHUNKS_PER_FILE
    out = capsys.readouterr().out
    assert "Capping" in out
    assert file_name in out
    assert f"{over_cap:,}" in out
    assert f"{ip.MAX_CHUNKS_PER_FILE:,}" in out


def test_parse_pdf_reads_bracket_filename_via_python_open(tmp_path: Path) -> None:
    """Bracket filenames must be read with Python open(), not Spark read_files glob."""
    file_name = "CIM [CONFIDENTIAL Draft].pdf"
    file_path = tmp_path / file_name
    file_path.write_bytes(b"%PDF-1.4\n" + b"x" * 64)

    open_paths: list[str] = []
    real_open = builtins.open

    def _tracking_open(path, *args, **kwargs):
        open_paths.append(str(path))
        return real_open(path, *args, **kwargs)

    spark = _mock_spark_for_pdf(_pdf_parse_result())
    with patch("builtins.open", side_effect=_tracking_open):
        chunks = ip.parse_pdf(str(file_path), _DOC_ID, file_name, spark)

    assert any("[" in p and "]" in p for p in open_paths)
    assert chunks
    assert all(c.file_name == file_name for c in chunks)


def test_parse_file_dispatches_bracket_named_pdf_to_parse_pdf() -> None:
    file_name = "Deal Memo [Final v3].pdf"
    fake_path = f"/tmp/{file_name}"
    captured: dict[str, str] = {}

    def _capture_pdf(file_path: str, doc_id: str, fname: str, spark, **kwargs) -> list[ip.Chunk]:
        captured["file_path"] = file_path
        captured["file_name"] = fname
        return [_stub_chunk(fname, "pdf")]

    with patch("ingestion_parser.parse_pdf", side_effect=_capture_pdf) as mock_pdf:
        ip.parse_file(fake_path, _DOC_ID, MagicMock())

    mock_pdf.assert_called_once()
    assert captured["file_name"] == file_name
    assert captured["file_path"] == fake_path


def test_get_embeddings_batch_single_call_for_exactly_twenty() -> None:
    client = MagicMock()
    texts = [_LONG_TEXT] * 20
    client.predict.return_value = {
        "data": [{"embedding": [0.1, 0.2]} for _ in range(20)],
        "usage": {},
    }

    result = ip.get_embeddings_batch(texts, client, "databricks-bge-large-en", batch_size=20)

    assert client.predict.call_count == 1
    call_inputs = client.predict.call_args.kwargs["inputs"]["input"]
    assert len(call_inputs) == 20
    assert len(result) == 20


def test_get_embeddings_batch_splits_twenty_one_into_two_calls() -> None:
    client = MagicMock()

    def _predict(*, endpoint: str, inputs: dict):
        batch = inputs["input"]
        return {
            "data": [{"embedding": [float(i)]} for i in range(len(batch))],
            "usage": {},
        }

    client.predict.side_effect = _predict
    texts = [_LONG_TEXT] * 21

    result = ip.get_embeddings_batch(texts, client, "databricks-bge-large-en", batch_size=20)

    assert client.predict.call_count == 2
    first_batch = client.predict.call_args_list[0].kwargs["inputs"]["input"]
    second_batch = client.predict.call_args_list[1].kwargs["inputs"]["input"]
    assert len(first_batch) == 20
    assert len(second_batch) == 1
    assert len(result) == 21


def test_get_embeddings_batch_raises_on_oversized_chunk() -> None:
    client = MagicMock()
    oversized = "x" * (ip.MAX_CHUNK_CHARS + 1)

    with pytest.raises(ValueError, match="exceed MAX_CHUNK_CHARS"):
        ip.get_embeddings_batch([oversized], client, "databricks-bge-large-en")


def test_parse_file_skips_unsupported_extension(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("ingestion_parser.parse_pdf") as mock_pdf, patch(
        "ingestion_parser.parse_excel"
    ) as mock_excel, patch("ingestion_parser.parse_word") as mock_word, patch(
        "ingestion_parser.parse_csv"
    ) as mock_csv:
        result = ip.parse_file("/tmp/archive.zip", _DOC_ID, MagicMock())

    assert result == []
    mock_pdf.assert_not_called()
    mock_excel.assert_not_called()
    mock_word.assert_not_called()
    mock_csv.assert_not_called()
    assert "skipped unsupported type" in capsys.readouterr().out
