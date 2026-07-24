"""UC13 Orchestrator — soft quality gates for rendered TL;DR one-pager (spec §2.3).

Reads ``{reports_volume_dir(catalog, company)}/tldr_one_pager.md`` and prints a
pass/warn summary table. Gates are **soft**: warnings print but the process
exits 0 unless the file is missing or unreadable (exit 1 on I/O error only).

CLI::

    python -m agents.orchestrator.tldr_quality_check --catalog uc13_ale --company "Elder Care"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

from agents.orchestrator.demo_walkthrough import get_param
from agents.orchestrator.formatters import is_operator_gap
from agents.orchestrator.paths import reports_volume_dir

_WORD_COUNT_WARN = 1200
_WORD_COUNT_STRETCH = 800
_DICT_LEAK_SUBSTRING = "{'metric':"


def _ascii_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        widths = [len(h) for h in headers]
    else:
        widths = [
            max(len(headers[i]), *(len(row[i]) for row in rows))
            for i in range(len(headers))
        ]

    def _row(cells: Sequence[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)) + " |"

    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [border, _row(headers), border]
    lines.extend(_row(row) for row in rows)
    lines.append(border)
    return "\n".join(lines)


def _word_count(body: str) -> int:
    return len(re.findall(r"\S+", body))


def _check_word_count(body: str) -> tuple[str, str]:
    count = _word_count(body)
    if count > _WORD_COUNT_WARN:
        return (
            "warn",
            f"{count} words (limit {_WORD_COUNT_WARN}; stretch goal {_WORD_COUNT_STRETCH})",
        )
    if count > _WORD_COUNT_STRETCH:
        return ("pass", f"{count} words (within {_WORD_COUNT_WARN}; above stretch {_WORD_COUNT_STRETCH})")
    return ("pass", f"{count} words (within stretch goal {_WORD_COUNT_STRETCH})")


def _check_dict_leak(body: str) -> tuple[str, str]:
    if _DICT_LEAK_SUBSTRING in body:
        return ("warn", f"found {_DICT_LEAK_SUBSTRING!r} substring (raw dict leak)")
    return ("pass", "no dict-shaped flag leak")


def _check_operator_gaps(body: str) -> tuple[str, str]:
    hits: list[str] = []
    for line_no, line in enumerate(body.splitlines(), start=1):
        if is_operator_gap(line):
            snippet = line.strip()
            if len(snippet) > 60:
                snippet = snippet[:57] + "..."
            hits.append(f"line {line_no}: {snippet}")
    if hits:
        preview = "; ".join(hits[:3])
        if len(hits) > 3:
            preview += f"; +{len(hits) - 3} more"
        return ("warn", f"operator-gap vocabulary ({preview})")
    return ("pass", "no operator-gap substrings")


def _run_gates(body: str) -> list[tuple[str, str, str]]:
    checks = (
        ("word_count", _check_word_count(body)),
        ("dict_leak", _check_dict_leak(body)),
        ("operator_gaps", _check_operator_gaps(body)),
    )
    return [(name, status, detail) for name, (status, detail) in checks]


def run(company_name: str | None = None, catalog: str | None = None) -> int:
    """Execute soft TL;DR quality gates; return 0 on success, 1 on I/O failure."""
    company_name = company_name or get_param("sp_company_name", "Elder Care")
    catalog = catalog or get_param("catalog", "uc13_ale")

    vol_dir = reports_volume_dir(catalog, company_name)
    md_path = Path(f"{vol_dir}/tldr_one_pager.md")

    if not md_path.is_file():
        print(f"[orchestrator] TLDR quality FAIL: file not found: {md_path}")
        return 1

    try:
        body = md_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[orchestrator] TLDR quality FAIL: cannot read {md_path}: {exc}")
        return 1

    print(f"[orchestrator] TLDR quality check: {md_path}")
    results = _run_gates(body)
    rows = [[name, status.upper(), detail] for name, status, detail in results]
    print(_ascii_table(["Gate", "Status", "Detail"], rows))

    warn_count = sum(1 for _, status, _ in results if status == "warn")
    if warn_count:
        print(f"\n[orchestrator] TLDR quality WARN — {warn_count} soft gate(s) triggered (exit 0)")
    else:
        print("\n[orchestrator] TLDR quality PASS — all soft gates clear")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Soft quality gates for rendered orchestrator tldr_one_pager.md",
    )
    parser.add_argument("--catalog", required=True, help="Unity Catalog name (e.g. uc13_ale)")
    parser.add_argument("--company", required=True, help='Company name (e.g. "Elder Care")')
    args = parser.parse_args(argv)
    return run(company_name=args.company, catalog=args.catalog)


if __name__ == "__main__":
    raise SystemExit(main())
