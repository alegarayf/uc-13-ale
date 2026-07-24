"""
run_diligence_pipeline.py — Databricks job entry point for the diligence pipeline.

This is the thin, single-task wrapper the Databricks job runs. It does NOT re-declare
the DAG — it simply resolves params, puts the repo on sys.path, and delegates to
``agents.orchestration.pipeline.run_pipeline()``, which owns the Phase 3 → 5 DAG,
parallelism, retry, and failure isolation (the single source of truth).

Invocation (spark_python_task passes parameters positionally as argv):
    run_diligence_pipeline.py <sp_company_name> [catalog] [llm_endpoint] [extraction_endpoint]

Falls back to widgets / os.environ when argv is not provided (e.g. run from a notebook).
The run manifest is printed and returned; the Orchestrator persists the final memo
(.md + .docx) and the uc13.analysis.diligence_report row.
"""

import os
import sys
from pathlib import Path


def _find_repo_root(marker: str = "agents") -> str:
    candidates = [Path.cwd(), Path(__file__).resolve().parent]
    for start in candidates:
        for c in [start, *start.parents]:
            if (c / marker).exists():
                return str(c)
    raise RuntimeError(f"Could not find a parent directory containing '{marker}'")


def main():
    argv = sys.argv[1:]

    def _arg(i, key, default=None):
        if i < len(argv) and argv[i]:
            return argv[i]
        return os.environ.get(key, default)

    company_name        = _arg(0, "sp_company_name")
    catalog             = _arg(1, "catalog", "uc13")
    llm_endpoint        = _arg(2, "llm_endpoint", "databricks-claude-sonnet-4-6")
    extraction_endpoint = _arg(3, "extraction_endpoint", llm_endpoint)

    if not company_name:
        raise RuntimeError("sp_company_name is required (argv[0], widget, or env var).")

    # Mirror into os.environ so each agent's get_param() fallback reads consistent values
    # inside worker threads (dbutils.widgets is unreliable from imported modules).
    os.environ["sp_company_name"]    = company_name
    os.environ["catalog"]            = catalog
    os.environ["llm_endpoint"]       = llm_endpoint
    os.environ["extraction_endpoint"] = extraction_endpoint

    repo_root = _find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from agents.orchestration.pipeline import run_pipeline

    print(f"=== Diligence pipeline job: {company_name} (catalog={catalog}) ===")
    manifest = run_pipeline(
        company_name=company_name,
        catalog=catalog,
        llm_endpoint=llm_endpoint,
        extraction_endpoint=extraction_endpoint,
        run_orchestrator=True,
    )

    # Surface a hard failure to the job UI only if EVERYTHING failed — partial
    # failures are expected/allowed (failure isolation) and are captured in the manifest.
    summary = manifest.get("summary", {})
    if summary.get("SUCCESS", 0) == 0:
        raise RuntimeError(f"All agents failed — see manifest: {manifest}")
    return manifest


if __name__ == "__main__":
    main()
