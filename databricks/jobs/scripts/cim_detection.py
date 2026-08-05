"""CIM (Confidential Information Memorandum) detection for the CIM-first
Rainmaker POC (docs/plans/CIM-first-rainmaker-template/plan.md §4/§6).

Single source of truth for the CIM name-match patterns: extends and replaces
the ``("CIM", [...])`` entry that used to live inline in
``download_upload._PRIORITY_SIGNALS`` — that module now imports
``CIM_NAME_PATTERNS`` from here instead of duplicating the list.

Verified against real CIMs in `uc13`/`uc13_ale` (plan §0.5):
  - Clearsulting: "Project Infinity - Confidential Information Memorandum.pdf"
    — no "CIM" in the name, but the full phrase IS in the filename, so a
    name/path regex match is sufficient (no full-text content parsing needed).
  - Elder Care: "2024 Elder Care - CIM_vF.pdf" — direct "CIM" match.
  - GKF: "Project Ajax CIM vF - Rallyday Partners.pdf" — direct match, but the
    same "CIM" SharePoint folder also holds a Teaser and an IOI process
    letter that are NOT the memorandum — must be excluded.

Content-based confirmation (parsing the candidate's extracted text rather
than its filename) is intentionally NOT implemented here: it was not needed
to correctly resolve any of the three real cases above, and would require a
parsed-text dependency this module doesn't otherwise need. If a future CIM
has a fully generic filename, extend ``detect_cim`` with an optional
content-confirmation hook rather than building it speculatively now.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Name/path match patterns — applied to "{relative_path}/{file_name}" lowercased
# (same convention as download_upload.detect_priority_tier).
# ---------------------------------------------------------------------------

CIM_NAME_PATTERNS: list[str] = [
    "cim",
    "confidential information memorandum",
    "offering memorandum",
    "investment overview",
    "information memorandum",
    "investment memorandum",
    "management presentation",
    r"\bom\b",
    r"\bconfidential\b.*\bmemorandum\b",
]

# Files matching a name pattern above are still excluded if they also match
# one of these — a Teaser or an IOI process letter is explicitly NOT the CIM,
# even when it lives in a folder/filename that otherwise looks CIM-like.
CIM_EXCLUDE_PATTERNS: list[str] = [
    "teaser",
    r"\bioi\b",
    "process letter",
    r"\bnda\b",
]

_CIM_NAME_RE = re.compile("|".join(CIM_NAME_PATTERNS), re.IGNORECASE)
_CIM_EXCLUDE_RE = re.compile("|".join(CIM_EXCLUDE_PATTERNS), re.IGNORECASE)


class _FileLike(Protocol):
    name: str
    relative_path: str
    size_bytes: int


def _target(file: _FileLike) -> str:
    return f"{getattr(file, 'relative_path', '') or ''}/{getattr(file, 'name', '') or ''}".lower()


def is_cim_candidate(file: _FileLike) -> bool:
    """True if *file*'s name/path matches a CIM pattern and no exclusion pattern."""
    target = _target(file)
    if _CIM_EXCLUDE_RE.search(target):
        return False
    return bool(_CIM_NAME_RE.search(target))


def _matches_special_folder(file: _FileLike, special_folder: str) -> bool:
    if not special_folder:
        return False
    folder_parts = {p.strip().lower() for p in getattr(file, "relative_path", "").split("/")}
    return special_folder.strip().lower() in folder_parts


def select_cim_files(files: list[_FileLike]) -> list[_FileLike]:
    """Pure, offline filter: CIM-name-matching, non-excluded files.

    When more than one candidate matches (e.g. a "CIM" folder containing both
    the real memorandum and a smaller supporting deck), the largest file
    (``size_bytes``) is treated as the actual memorandum and returned first —
    a bigger CIM-tagged document is far more likely to be the real memo than
    a companion one-pager, and this needs no content parsing to decide.
    """
    candidates = [f for f in files if is_cim_candidate(f)]
    return sorted(candidates, key=lambda f: getattr(f, "size_bytes", 0), reverse=True)


def select_special_folder_files(files: list[_FileLike], special_folder: str) -> list[_FileLike]:
    """All files under *special_folder* (case-insensitive folder-segment match)."""
    return [f for f in files if _matches_special_folder(f, special_folder)]


def detect_cim(
    company_name: str,
    connector: Any,
    special_folder: str = "",
) -> list[str]:
    """Return the file name(s) to treat as the CIM-first preview basis.

    ``connector`` only needs to expose ``list_files() -> list[FileMetadata]``
    (duck-typed against ``agents.ingestion.tools.connector``, so tests can
    pass a lightweight stand-in without any SharePoint/network dependency).

    Resolution order:
      1. CIM name/path match (``select_cim_files``) — the primary, cheap gate.
      2. If none found and ``special_folder`` is set, fall back to every file
         under that folder (plan §4 — "sino existe [CIM]... folder especial").
      3. Otherwise, ``[]`` — the caller (run_vdr_rainmaker.py) no-ops with a
         message rather than generating a Rainmaker preview (plan §4, §8).
    """
    files = connector.list_files()

    cim_files = select_cim_files(files)
    if cim_files:
        return [f.name for f in cim_files]

    if special_folder:
        folder_files = select_special_folder_files(files, special_folder)
        return [f.name for f in folder_files]

    return []
