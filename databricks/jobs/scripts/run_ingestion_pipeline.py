"""
run_ingestion_pipeline.py — Phase 1-2 ingestion pipeline entry point.

Runs the four Phase 1-2 scripts in strict dependency order:
  Phase 1  : download_upload      → UC Volume files + upload_log
  Phase 2a : document_classifier  → doc_relevance (workstream tags, priority tier)
  Phase 2b : ingestion_parser     → chunks + embeddings (triggers VS index sync)
  Phase 2b : company_profiler     → company_profile (overlay, deal type)

Failure isolation:
  - download_upload FAILED  → classifier / parser / profiler all SKIPPED (no files).
  - document_classifier FAILED → parser + profiler SKIPPED (no doc_relevance rows).
  - ingestion_parser FAILED → profiler runs DEGRADED (semantic search finds no chunks).
  - company_profiler FAILED → pipeline returns partial SUCCESS; Phase 3-5 can still
    run (overlay detection will fall back to CIM heuristics inside each agent).

Invocation (spark_python_task positional argv):
    run_ingestion_pipeline.py <sp_company_name> [catalog] [schema]
                              [embedding_endpoint] [vision_endpoint]

Also callable as a Python function from run_full_pipeline.py or a notebook::

    from run_ingestion_pipeline import run_ingestion_pipeline
    summary = run_ingestion_pipeline(company_name="Elder Care", ...)
"""

import importlib
import importlib.util
import os
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _find_scripts_dir() -> str:
    """Return the abs path of the directory containing the Phase 1-2 scripts."""
    here = Path(__file__).resolve().parent
    if (here / "download_upload.py").exists():
        return str(here)
    for start in (Path.cwd(), here):
        for c in [start, *start.parents]:
            s = c / "jobs" / "scripts"
            if (s / "download_upload.py").exists():
                return str(s)
    raise RuntimeError(
        "Cannot locate jobs/scripts directory (download_upload.py not found). "
        "Ensure the Databricks repo checkout includes databricks/jobs/scripts/."
    )


def _find_repo_root(scripts_dir: str) -> str:
    """Return the repo root (the directory that contains the 'agents' package)."""
    for c in [Path(scripts_dir), *Path(scripts_dir).parents]:
        if (c / "agents").exists():
            return str(c)
    raise RuntimeError(
        "Cannot locate repo root (no 'agents' subdirectory found above scripts_dir). "
        f"scripts_dir={scripts_dir!r}"
    )


# ---------------------------------------------------------------------------
# Module loader (same pattern as pipeline.py _invoke)
# ---------------------------------------------------------------------------

def _import_script(module_name: str, scripts_dir: str):
    """Load a script by file path, registering it in sys.modules for reuse.

    This avoids issues with module_name clashes and lets each script's
    get_param() fallback see the os.environ values already set.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    path = os.path.join(scripts_dir, module_name + ".py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Script not found: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

def run_ingestion_pipeline(
    company_name: str,
    catalog: str = "uc13",
    schema: str = "ingestion",
    embedding_endpoint: str = "databricks-bge-large-en",
    vision_endpoint: str = "",
    parse_priority_tiers: str = "1,2",
    skip_download: bool = False,
    force: str = "none",
    coverage_per_workstream: int = 3,
    skip_sync: bool = False,
    sync_only: bool = False,
) -> dict:
    """Run Phase 1-2 in dependency order and return a step-by-step summary.

    Returns::

        {
            "company_name": str,
            "phases": {
                "download_upload":     {"status": "SUCCESS"|"FAILED"|"SKIPPED",
                                        "duration_s": float, "error": str|None},
                "document_classifier": {...},
                "ingestion_parser":    {...},
                "company_profiler":    {...},
            },
            "summary": {"SUCCESS": int, "FAILED": int, "SKIPPED": int},
        }
    """
    # Mirror all params into os.environ so each script's get_param() fallback
    # works when the script is loaded as an imported module (where
    # dbutils.widgets is not accessible as a direct global).
    os.environ["sp_company_name"]      = company_name
    os.environ["catalog"]              = catalog
    os.environ["schema"]               = schema
    os.environ["embedding_endpoint"]   = embedding_endpoint
    # company_profiler reads llm_endpoint via get_param; default to LLaMA for Phase 1-2
    # (document_classifier hardcodes its endpoint — doesn't read from env).
    # This value is overridden by run_full_pipeline before calling run_pipeline().
    if "llm_endpoint" not in os.environ:
        os.environ["llm_endpoint"] = "databricks-meta-llama-3-3-70b-instruct"
    os.environ["vision_endpoint"]      = vision_endpoint
    os.environ["parse_priority_tiers"] = parse_priority_tiers
    os.environ["force"]                = force
    os.environ["coverage_per_workstream"] = str(coverage_per_workstream)
    os.environ["skip_sync"]            = "true" if skip_sync else "false"
    os.environ["sync_only"]            = "true" if sync_only else "false"

    scripts_dir = _find_scripts_dir()
    repo_root   = _find_repo_root(scripts_dir)
    for p in (repo_root, scripts_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    phases: dict = {}

    def _run(label: str, module_name: str, func_name: str = "main") -> dict:
        t0 = time.time()
        try:
            mod = _import_script(module_name, scripts_dir)
            getattr(mod, func_name)()
            dur = round(time.time() - t0, 1)
            print(f"  ✓ {label} — {dur}s")
            return {"status": "SUCCESS", "duration_s": dur}
        except Exception as exc:
            dur = round(time.time() - t0, 1)
            print(f"  ✗ {label} — FAILED in {dur}s: {exc}")
            return {"status": "FAILED", "duration_s": dur, "error": str(exc)}

    def _skip(label: str, reason: str) -> dict:
        print(f"  ⏭  {label} — SKIPPED ({reason})")
        return {"status": "SKIPPED", "error": reason}

    print(f"\n=== Ingestion Pipeline: {company_name} (catalog={catalog}) ===")

    # ── Phase 1: Download + upload to UC Volume ──────────────────────────
    if skip_download:
        phases["download_upload"] = _skip(
            "Phase 1: Download + Upload", "skip_download=True"
        )
    else:
        phases["download_upload"] = _run(
            "Phase 1: Download + Upload", "download_upload"
        )
        if phases["download_upload"]["status"] == "FAILED":
            phases["document_classifier"] = _skip(
                "Phase 2a: Document Classifier", "download_upload failed — no files in Volume"
            )
            phases["ingestion_parser"] = _skip(
                "Phase 2b: Ingestion Parser", "download_upload failed — no files in Volume"
            )
            phases["company_profiler"] = _skip(
                "Phase 2b: Company Profiler", "download_upload failed — no files in Volume"
            )
            return _build_summary(company_name, phases)

    # ── Phase 2a: Document Classifier ────────────────────────────────────
    phases["document_classifier"] = _run(
        "Phase 2a: Document Classifier", "document_classifier"
    )
    if phases["document_classifier"]["status"] == "FAILED":
        phases["ingestion_parser"] = _skip(
            "Phase 2b: Ingestion Parser",
            "document_classifier failed — doc_relevance table not populated"
        )
        phases["company_profiler"] = _skip(
            "Phase 2b: Company Profiler",
            "document_classifier failed — doc_relevance table not populated"
        )
        return _build_summary(company_name, phases)

    # ── Phase 2b: Ingestion Parser (also triggers VS index sync) ─────────
    phases["ingestion_parser"] = _run("Phase 2b: Ingestion Parser", "ingestion_parser")
    if phases["ingestion_parser"]["status"] == "FAILED":
        # Profiler will degrade gracefully — semantic search finds no chunks.
        print(
            "  [warn] Parser failed — Company Profiler will run degraded "
            "(no embeddings; profile fields will be null)."
        )

    # ── Phase 2b: Company Profiler ────────────────────────────────────────
    phases["company_profiler"] = _run("Phase 2b: Company Profiler", "company_profiler")

    return _build_summary(company_name, phases)


def _build_summary(company_name: str, phases: dict) -> dict:
    s  = sum(1 for v in phases.values() if v.get("status") == "SUCCESS")
    f  = sum(1 for v in phases.values() if v.get("status") == "FAILED")
    sk = sum(1 for v in phases.values() if v.get("status") == "SKIPPED")
    print(f"\n=== Ingestion complete: {s} SUCCESS · {f} FAILED · {sk} SKIPPED ===")
    return {
        "company_name": company_name,
        "phases":       phases,
        "summary":      {"SUCCESS": s, "FAILED": f, "SKIPPED": sk},
    }


# ---------------------------------------------------------------------------
# Job entry point
# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[1:]

    def _arg(i, key, default=None):
        if i < len(argv) and argv[i]:
            return argv[i]
        return os.environ.get(key, default)

    def _bool_arg(i, key, default="false"):
        raw = _arg(i, key, default)
        return str(raw).strip().lower() in ("true", "1", "yes")

    company_name         = _arg(0, "sp_company_name")
    catalog              = _arg(1, "catalog",              "uc13")
    schema               = _arg(2, "schema",               "ingestion")
    embedding_endpoint   = _arg(3, "embedding_endpoint",   "databricks-bge-large-en")
    vision_endpoint      = _arg(4, "vision_endpoint",      "")
    parse_priority_tiers = _arg(5, "parse_priority_tiers", "1,2")
    force                = _arg(6, "force", "none")
    coverage_per_workstream = int(_arg(7, "coverage_per_workstream", "3"))
    skip_sync            = _bool_arg(8, "skip_sync", "false")
    sync_only            = _bool_arg(9, "sync_only", "false")

    if not company_name:
        raise RuntimeError(
            "sp_company_name is required (argv[0], widget, or env var sp_company_name)."
        )

    os.environ["sp_company_name"]      = company_name
    os.environ["catalog"]              = catalog
    os.environ["schema"]               = schema
    os.environ["embedding_endpoint"]   = embedding_endpoint
    os.environ["vision_endpoint"]      = vision_endpoint
    os.environ["parse_priority_tiers"] = parse_priority_tiers
    os.environ["force"]                = force
    os.environ["coverage_per_workstream"] = str(coverage_per_workstream)
    os.environ["skip_sync"]            = "true" if skip_sync else "false"
    os.environ["sync_only"]            = "true" if sync_only else "false"

    summary = run_ingestion_pipeline(
        company_name=company_name,
        catalog=catalog,
        schema=schema,
        embedding_endpoint=embedding_endpoint,
        vision_endpoint=vision_endpoint,
        parse_priority_tiers=parse_priority_tiers,
        force=force,
        coverage_per_workstream=coverage_per_workstream,
        skip_sync=skip_sync,
        sync_only=sync_only,
    )

    # Surface a hard failure to the Databricks job UI only if ALL steps that
    # were not intentionally skipped have failed.
    active_failures = sum(
        1 for v in summary["phases"].values()
        if v.get("status") == "FAILED"
    )
    if active_failures > 0 and summary["summary"]["SUCCESS"] == 0:
        raise RuntimeError(
            f"All ingestion steps failed — see phase summary: {summary['phases']}"
        )
    return summary


if __name__ == "__main__":
    main()
