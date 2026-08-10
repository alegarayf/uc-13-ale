"""Canonical doc_id construction for UC-13 ingestion (M0 frozen contract)."""

from __future__ import annotations

import hashlib
import posixpath


def make_doc_id(
    catalog: str,
    schema: str,
    company: str,
    folder_path: str | None,
    file_name: str,
) -> str:
    """Build canonical volume path and return its md5 hexdigest.

    Path shape: /Volumes/{catalog}/{schema}/raw_files/{company}/[folder_path/]file_name
  folder_path in {None, "", "."} drops the folder segment. No trailing slash on the
    final path. Byte-identical to ingestion_parser main() path construction on Linux.
    """
    volume_path = f"/Volumes/{catalog}/{schema}/raw_files/{company}"
    if folder_path not in ("", ".", None):
        path = posixpath.join(volume_path, folder_path, file_name)
    else:
        path = posixpath.join(volume_path, file_name)
    return hashlib.md5(path.encode()).hexdigest()
