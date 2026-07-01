"""Shared retrieval types — import shim to avoid circular imports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RouteResult:
    chunks: list  # Spark Rows: chunk_id, file_name, chunk_text, section_header,
                  # page_start, source_type, workstream, priority_tier
    mode: str     # "semantic" | "keyword" | "empty" — §5.16 retrieval_execution_mode
    scores: list[float]  # parallel to chunks; non-empty when chunks non-empty (enforced T2)
