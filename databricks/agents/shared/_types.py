"""Shared retrieval types — import shim to avoid circular imports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RouteResult:
    chunks: list  # Spark Rows: chunk_id, file_name, chunk_text, section_header,
                  # page_start, source_type, workstream, priority_tier
    mode: str     # "routed" | "semantic" | "keyword_fallback"
    scores: list | None = None
