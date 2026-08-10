"""doc_id equality contract for parse_file (M1 / T1).

For a given (catalog, schema, company, folder_path, file_name), the doc_id
StatusStore/ParseManifest would use via doc_id.make_doc_id must be byte-identical
to the doc_id parse_file receives and stamps onto every returned Chunk.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from doc_id import make_doc_id  # noqa: E402
import ingestion_parser as ip  # noqa: E402

_CATALOG = "uc13"
_SCHEMA = "ingestion"
_COMPANY = "Elder Care"


def _stub_chunk(doc_id: str, file_name: str, file_path: str) -> ip.Chunk:
    return ip.Chunk(
        chunk_id="test-chunk",
        doc_id=doc_id,
        file_name=file_name,
        file_type="csv",
        relative_path=file_path,
        chunk_index=0,
        chunk_text="x" * 200,
    )


@pytest.mark.parametrize(
    ("folder_path", "file_name"),
    [
        (None, "root.csv"),
        ("Financials", "model.csv"),
        ("reports/", "summary.csv"),
        ("a/b", "nested.csv"),
    ],
)
def test_parse_file_stamps_caller_doc_id_on_chunks(
    folder_path: str | None,
    file_name: str,
) -> None:
    expected_doc_id = make_doc_id(_CATALOG, _SCHEMA, _COMPANY, folder_path, file_name)
    captured: dict[str, str] = {}

    def fake_parse_csv(file_path: str, doc_id: str, fname: str) -> list[ip.Chunk]:
        captured["doc_id"] = doc_id
        return [_stub_chunk(doc_id, fname, file_path)]

    fake_path = f"/tmp/{file_name}"
    with patch("ingestion_parser.parse_csv", side_effect=fake_parse_csv):
        chunks = ip.parse_file(fake_path, expected_doc_id, MagicMock())

    assert captured["doc_id"] == expected_doc_id
    assert chunks
    assert all(c.doc_id == expected_doc_id for c in chunks)


def test_parse_file_does_not_recompute_doc_id_from_path() -> None:
    """Falsifier: parse_file must not derive doc_id internally from file_path."""
    file_name = "mismatch.csv"
    canonical_doc_id = make_doc_id(_CATALOG, _SCHEMA, _COMPANY, "Legal", file_name)
    wrong_doc_id = "00000000000000000000000000000000"
    captured: dict[str, str] = {}

    def fake_parse_csv(file_path: str, doc_id: str, fname: str) -> list[ip.Chunk]:
        captured["doc_id"] = doc_id
        return [_stub_chunk(doc_id, fname, file_path)]

    fake_path = f"/tmp/{file_name}"
    with patch("ingestion_parser.parse_csv", side_effect=fake_parse_csv):
        chunks = ip.parse_file(fake_path, wrong_doc_id, MagicMock())

    assert wrong_doc_id != canonical_doc_id
    assert captured["doc_id"] == wrong_doc_id
    assert all(c.doc_id == wrong_doc_id for c in chunks)
