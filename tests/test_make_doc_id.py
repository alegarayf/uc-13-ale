"""Contract-test subset for doc_id.make_doc_id (M0 / T1)."""

from __future__ import annotations

import hashlib
import posixpath
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from doc_id import make_doc_id  # noqa: E402

_CATALOG = "uc13"
_SCHEMA = "ingestion"
_COMPANY = "Elder Care"


def _reference_path(
    catalog: str,
    schema: str,
    company: str,
    folder_path: str | None,
    file_name: str,
) -> str:
    """Mirror ingestion_parser.py main() path build (posix semantics for off-cluster)."""
    volume_path = f"/Volumes/{catalog}/{schema}/raw_files/{company}"
    if folder_path not in ("", ".", None):
        return posixpath.join(volume_path, folder_path, file_name)
    return posixpath.join(volume_path, file_name)


def _reference_doc_id(
    catalog: str,
    schema: str,
    company: str,
    folder_path: str | None,
    file_name: str,
) -> str:
    return hashlib.md5(
        _reference_path(catalog, schema, company, folder_path, file_name).encode()
    ).hexdigest()


@pytest.mark.parametrize("folder_path", [None, "", "."])
def test_folder_path_sentinels_drop_segment(folder_path: str | None) -> None:
    file_name = "annual_report.pdf"
    expected_path = f"/Volumes/{_CATALOG}/{_SCHEMA}/raw_files/{_COMPANY}/{file_name}"
    assert _reference_path(_CATALOG, _SCHEMA, _COMPANY, folder_path, file_name) == expected_path
    assert make_doc_id(_CATALOG, _SCHEMA, _COMPANY, folder_path, file_name) == hashlib.md5(
        expected_path.encode()
    ).hexdigest()


def test_importable_and_identical_hash_for_identical_args() -> None:
    args = (_CATALOG, _SCHEMA, _COMPANY, "Financials", "model.xlsx")
    first = make_doc_id(*args)
    second = make_doc_id(*args)
    assert first == second
    assert len(first) == 32


def test_trailing_slash_on_folder_path_suppressed() -> None:
    with_slash = make_doc_id(_CATALOG, _SCHEMA, _COMPANY, "reports/", "file.pdf")
    without_slash = make_doc_id(_CATALOG, _SCHEMA, _COMPANY, "reports", "file.pdf")
    assert with_slash == without_slash


def test_bracket_and_metacharacter_filenames() -> None:
    file_name = "deck [final] (v2).pdf"
    folder_path = "CIM/2024"
    doc_id = make_doc_id(_CATALOG, _SCHEMA, _COMPANY, folder_path, file_name)
    expected_path = (
        f"/Volumes/{_CATALOG}/{_SCHEMA}/raw_files/{_COMPANY}/{folder_path}/{file_name}"
    )
    assert doc_id == hashlib.md5(expected_path.encode()).hexdigest()


def test_nested_folder_path_segments() -> None:
    folder_path = "a/b"
    file_name = "c.pdf"
    doc_id = make_doc_id(_CATALOG, _SCHEMA, _COMPANY, folder_path, file_name)
    assert doc_id == _reference_doc_id(_CATALOG, _SCHEMA, _COMPANY, folder_path, file_name)


@pytest.mark.parametrize(
    ("folder_path", "file_name"),
    [
        (None, "root_level.docx"),
        ("Legal", "contract.pdf"),
        ("reports/", "summary.xlsx"),
        ("a/b", "c.pdf"),
        (".", "dot_sentinel.csv"),
        ("", "empty_folder_sentinel.csv"),
        ("Financials", "file[1].pdf"),
    ],
)
def test_path_byte_identity_vs_reference_construction(
    folder_path: str | None,
    file_name: str,
) -> None:
    assert make_doc_id(_CATALOG, _SCHEMA, _COMPANY, folder_path, file_name) == _reference_doc_id(
        _CATALOG, _SCHEMA, _COMPANY, folder_path, file_name
    )


def test_different_catalog_changes_doc_id() -> None:
    """Falsifier: doc_id must incorporate catalog, not only file_name."""
    elder = make_doc_id("uc13", _SCHEMA, _COMPANY, None, "same.pdf")
    eval_catalog = make_doc_id("uc13_ale", _SCHEMA, _COMPANY, None, "same.pdf")
    assert elder != eval_catalog
