"""Dual baseline compare for M3 E2E (D4-A).

Arm 1 — legacy ``legal_contracts_report.yaml`` vs A1 baseline YAML.
Arm 2 — normative ``legal_report.yaml`` vs Stakeholder Report Outline keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from databricks.sdk import WorkspaceClient

_PKG_DIR = Path(__file__).resolve().parent
BASELINE_LEGACY = _PKG_DIR / "baselines" / "baseline_elder_care_legal_contracts_report.yaml"
TMP_DIR = _PKG_DIR / "baselines"

# Stakeholder Report Outline top-level keys (spec §5.9 / m2-t6 dual-write).
NORMATIVE_OUTLINE_KEYS = (
    "report",
    "confidence",
    "executive_summary",
    "Customer & Vendor Contracts",
    "Platform & Channel Dependencies",
    "Employment & Founder Agreements",
    "Litigation & Disputes",
    "IP, Privacy & Security",
    "Insurance",
    "Flags",
    "Recommended Legal Diligence",
    "Data Room Gaps",
)


def volume_paths(catalog: str, company: str) -> tuple[str, str]:
    """Return (legacy_path, normative_path) for Elder-Care-style company slug."""
    safe = company.replace(" ", "_").replace("/", "_")
    base = f"/Volumes/{catalog}/analysis/reports/{safe}"
    return (
        f"{base}/legal_contracts_report.yaml",
        f"{base}/legal_report.yaml",
    )


def load_body(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return yaml.safe_load("\n".join(lines))


def download_volume(w: WorkspaceClient, volume_path: str, dest: Path) -> int:
    content = w.files.download(volume_path).contents.read()
    dest.write_bytes(content)
    return len(content)


def legacy_summary(doc: dict) -> dict:
    report = doc.get("report") or {}
    return {
        "agent": report.get("agent"),
        "company": report.get("company"),
        "generated_at": report.get("generated_at"),
        "contract_register_count": len(doc.get("contract_register") or []),
        "litigation_count": len(doc.get("litigation_register") or []),
        "flags_count": len(doc.get("flags") or []),
        "gaps_count": len(doc.get("data_room_gaps") or []),
        "citations_count": len(doc.get("citations") or []),
        "executive_summary_len": len(doc.get("executive_summary") or ""),
    }


def normative_summary(doc: dict) -> dict:
    report = doc.get("report") or {}
    cvc = doc.get("Customer & Vendor Contracts") or {}
    platform = doc.get("Platform & Channel Dependencies") or {}
    employment = doc.get("Employment & Founder Agreements") or {}
    litigation = doc.get("Litigation & Disputes") or {}
    ip_priv = doc.get("IP, Privacy & Security") or {}
    insurance = doc.get("Insurance") or {}
    return {
        "agent": report.get("agent"),
        "company": report.get("company"),
        "generated_at": report.get("generated_at"),
        "confidence": doc.get("confidence"),
        "contract_register_count": len(cvc.get("contract_register") or []),
        "vendor_register_count": len(cvc.get("vendor_register") or []),
        "platform_register_count": len(platform.get("platform_dependency_register") or []),
        "employment_register_count": len(employment.get("employment_register") or []),
        "litigation_count": len(litigation.get("litigation_register") or []),
        "ip_register_count": len(ip_priv.get("ip_register") or []),
        "privacy_register_count": len(ip_priv.get("privacy_security_register") or []),
        "insurance_register_count": len(insurance.get("insurance_register") or []),
        "flags_count": len(doc.get("Flags") or []),
        "gaps_count": len(doc.get("Data Room Gaps") or []),
        "diligence_count": len(doc.get("Recommended Legal Diligence") or []),
        "unable_to_assess_total": sum(
            len((doc.get(section) or {}).get("unable_to_assess") or [])
            for section in (
                "Customer & Vendor Contracts",
                "Platform & Channel Dependencies",
                "Employment & Founder Agreements",
                "Litigation & Disputes",
                "IP, Privacy & Security",
                "Insurance",
            )
        ),
        "executive_summary_len": len(doc.get("executive_summary") or ""),
    }


def outline_check(doc: dict) -> dict:
    present = set(doc.keys())
    expected = set(NORMATIVE_OUTLINE_KEYS)
    return {
        "missing_keys": sorted(expected - present),
        "extra_keys": sorted(present - expected - {"report"}),
        "outline_complete": expected.issubset(present),
    }


def diff_paths(a, b, prefix="") -> list[str]:
    diffs: list[str] = []
    if type(a) != type(b):
        return [f"{prefix}: type {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        keys = sorted(set(a) | set(b))
        for k in keys:
            p = f"{prefix}.{k}" if prefix else k
            if k not in a:
                diffs.append(f"{p}: missing in baseline")
            elif k not in b:
                diffs.append(f"{p}: missing in latest")
            else:
                diffs.extend(diff_paths(a[k], b[k], p))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{prefix}: list len {len(a)} != {len(b)}")
        for i, (ai, bi) in enumerate(zip(a, b)):
            diffs.extend(diff_paths(ai, bi, f"{prefix}[{i}]"))
    elif a != b:
        av = repr(a) if len(repr(a)) < 120 else repr(a)[:117] + "..."
        bv = repr(b) if len(repr(b)) < 120 else repr(b)[:117] + "..."
        diffs.append(f"{prefix}: {av} != {bv}")
    return diffs


def compare_legacy_arm(
    baseline_path: Path,
    latest_path: Path,
    *,
    max_diffs: int,
) -> dict:
    base = load_body(baseline_path)
    latest = load_body(latest_path)
    summary = {
        "baseline": legacy_summary(base),
        "latest": legacy_summary(latest),
    }
    if base == latest:
        summary["result"] = "IDENTICAL"
        summary["diff_count"] = 0
        summary["sample_diffs"] = []
    else:
        diffs = diff_paths(base, latest)
        summary["result"] = "DIFFER"
        summary["diff_count"] = len(diffs)
        summary["sample_diffs"] = diffs[:max_diffs]
    return summary


def compare_normative_arm(latest_path: Path) -> dict:
    latest = load_body(latest_path)
    outline = outline_check(latest)
    return {
        "latest": normative_summary(latest),
        "outline": outline,
        "result": "OUTLINE_OK" if outline["outline_complete"] else "OUTLINE_GAP",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M3 dual baseline compare (D4-A)")
    parser.add_argument("--catalog", default=os.environ.get("catalog", "uc13_ale"))
    parser.add_argument("--company", default=os.environ.get("sp_company_name", "Elder Care"))
    parser.add_argument(
        "--baseline",
        type=Path,
        default=BASELINE_LEGACY,
        help="A1 legacy baseline YAML path",
    )
    parser.add_argument(
        "--max-diffs",
        type=int,
        default=40,
        help="Max leaf diffs to print for legacy arm",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable summary only",
    )
    args = parser.parse_args(argv)

    legacy_vol, normative_vol = volume_paths(args.catalog, args.company)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    safe = args.company.replace(" ", "_").replace("/", "_")
    legacy_tmp = TMP_DIR / f"_latest_{safe}_legal_contracts_report.yaml"
    normative_tmp = TMP_DIR / f"_latest_{safe}_legal_report.yaml"

    w = WorkspaceClient()
    legacy_bytes = download_volume(w, legacy_vol, legacy_tmp)
    normative_bytes = download_volume(w, normative_vol, normative_tmp)

    legacy_arm = compare_legacy_arm(args.baseline, legacy_tmp, max_diffs=args.max_diffs)
    normative_arm = compare_normative_arm(normative_tmp)

    payload = {
        "catalog": args.catalog,
        "company": args.company,
        "volume_paths": {
            "legacy": legacy_vol,
            "normative": normative_vol,
        },
        "bytes": {
            "legacy": legacy_bytes,
            "normative": normative_bytes,
        },
        "arm1_legacy_vs_a1": legacy_arm,
        "arm2_normative_vs_outline": normative_arm,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Catalog: {args.catalog}  Company: {args.company}\n")
    print(f"Downloaded {legacy_bytes} bytes from {legacy_vol}")
    print(f"Downloaded {normative_bytes} bytes from {normative_vol}\n")

    print("=== Arm 1: legacy legal_contracts_report.yaml vs A1 baseline ===")
    print("A1 baseline:", json.dumps(legacy_arm["baseline"], indent=2))
    print("M3 latest:", json.dumps(legacy_arm["latest"], indent=2))
    print(f"RESULT: {legacy_arm['result']} ({legacy_arm['diff_count']} leaf differences)")
    for line in legacy_arm.get("sample_diffs") or []:
        print(" ", line)
    extra = legacy_arm["diff_count"] - len(legacy_arm.get("sample_diffs") or [])
    if extra > 0:
        print(f"  ... and {extra} more")

    print("\n=== Arm 2: normative legal_report.yaml vs Stakeholder Outline ===")
    print("M3 normative:", json.dumps(normative_arm["latest"], indent=2))
    print("Outline check:", json.dumps(normative_arm["outline"], indent=2))
    print(f"RESULT: {normative_arm['result']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
