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
_HEADLINE_TABLE_HEADER_RE = re.compile(r"^\|\s*Metric\s*\|\s*Value\s*\|", re.IGNORECASE)
_TABLE_SEPARATOR_RE = re.compile(r"^\|[-:| ]+\|$")
_SPIRIOUS_DOLLAR_RE = re.compile(r"^\$[\d,]+$")
_RISK_RAW_KEY_PATTERNS = ("tier4_addback", "open_legal_matter_other", _DICT_LEAK_SUBSTRING)


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


def _extract_headline_metric_rows(body: str) -> list[tuple[str, str]]:
    """Return (label, value) rows from the first ``| Metric | Value |`` table until ``---``."""
    lines = body.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if _HEADLINE_TABLE_HEADER_RE.match(line.strip()):
            start_idx = i
            break
    if start_idx is None:
        return []

    rows: list[tuple[str, str]] = []
    for line in lines[start_idx + 1 :]:
        stripped = line.strip()
        if stripped == "---" or stripped.startswith("## "):
            break
        if not stripped.startswith("|"):
            break
        if _TABLE_SEPARATOR_RE.match(stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2:
            rows.append((cells[0], cells[1]))
    return rows


def _extract_risk_table_rows(body: str) -> list[list[str]]:
    """Return data rows from the ``## Top Risks`` pipe table."""
    lines = body.splitlines()
    in_risks = False
    past_header = False
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "## Top Risks":
            in_risks = True
            continue
        if in_risks and stripped.startswith("## "):
            break
        if in_risks and stripped == "---":
            break
        if not in_risks or not stripped.startswith("|"):
            continue
        if _TABLE_SEPARATOR_RE.match(stripped):
            past_header = True
            continue
        if not past_header:
            if "Risk" in stripped and "Severity" in stripped:
                past_header = True
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells:
            rows.append(cells)
    return rows


def _check_headline_duplicate_labels(body: str) -> tuple[str, str]:
    rows = _extract_headline_metric_rows(body)
    if not rows:
        return ("pass", "no headline metric table found")
    counts: dict[str, int] = {}
    for label, _ in rows:
        counts[label] = counts.get(label, 0) + 1
    dupes = sorted(label for label, count in counts.items() if count > 1)
    if dupes:
        return ("warn", f"duplicate headline labels ({', '.join(dupes)})")
    return ("pass", "headline labels unique")


def _check_risk_raw_metric_keys(body: str) -> tuple[str, str]:
    hits: list[str] = []
    for row in _extract_risk_table_rows(body):
        row_text = " | ".join(row)
        for pattern in _RISK_RAW_KEY_PATTERNS:
            if pattern in row_text:
                hits.append(pattern)
                break
    if hits:
        unique = sorted(set(hits))
        return ("warn", f"raw metric keys in risk table ({', '.join(unique)})")
    return ("pass", "no raw metric keys in risk table")


def _check_headline_spurious_dollar(body: str) -> tuple[str, str]:
    hits: list[str] = []
    for label, value in _extract_headline_metric_rows(body):
        if label == "Revenue" and _SPIRIOUS_DOLLAR_RE.match(value.strip()):
            hits.append(f"Revenue={value}")
    if hits:
        return ("warn", f"spurious small-dollar Revenue ({', '.join(hits)})")
    return ("pass", "no spurious headline Revenue dollars")


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
        ("headline_duplicate_labels", _check_headline_duplicate_labels(body)),
        ("risk_raw_metric_keys", _check_risk_raw_metric_keys(body)),
        ("headline_spurious_dollar", _check_headline_spurious_dollar(body)),
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
