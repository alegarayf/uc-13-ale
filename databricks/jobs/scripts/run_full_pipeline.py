"""
run_full_pipeline.py — End-to-end diligence pipeline: Phase 1-5.

Chains run_ingestion_pipeline() (Phase 1-2) → run_pipeline() (Phase 3-5).
Use this when processing a new company for the first time, or when you want
a single notebook call to go from raw SharePoint files to a finished memo.

Use run_diligence_pipeline.py alone when embeddings are already populated
(Phase 1-2 has been run for this company) — it skips the download/parse and
goes straight to diligence agents.

Abort logic:
  - document_classifier FAILED or ingestion_parser FAILED → Phase 3-5 ABORTED.
    No embeddings → every retrieval tool in Phase 3 would return empty results.
  - company_profiler FAILED only → Phase 3-5 continues in degraded mode
    (overlay detection falls back to CIM heuristics in each agent).

Invocation (spark_python_task positional argv):
    run_full_pipeline.py <sp_company_name> [catalog] [schema]
                         [embedding_endpoint] [llm_endpoint]
                         [extraction_endpoint] [vision_endpoint]

Also callable as a Python function from a notebook::

    from run_full_pipeline import run_full_pipeline
    result = run_full_pipeline(company_name="Elder Care", ...)
    display(result["summary"])
"""

import inspect
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _find_scripts_dir() -> str:
    here = Path(inspect.getfile(_find_scripts_dir)).resolve().parent
    if (here / "run_ingestion_pipeline.py").exists():
        return str(here)
    for start in (Path.cwd(), here):
        for c in [start, *start.parents]:
            s = c / "jobs" / "scripts"
            if (s / "run_ingestion_pipeline.py").exists():
                return str(s)
    raise RuntimeError(
        "Cannot locate jobs/scripts directory (run_ingestion_pipeline.py not found)."
    )


def _find_repo_root(scripts_dir: str) -> str:
    for c in [Path(scripts_dir), *Path(scripts_dir).parents]:
        if (c / "agents").exists():
            return str(c)
    raise RuntimeError(
        f"Cannot locate repo root (no 'agents' directory found above {scripts_dir!r})."
    )


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

def run_full_pipeline(
    company_name: str,
    catalog: str = "uc13",
    schema: str = "ingestion",
    embedding_endpoint: str = "databricks-bge-large-en",
    llm_endpoint: str = "databricks-claude-sonnet-4-6",
    extraction_endpoint: str = "databricks-claude-sonnet-4-6",
    vision_endpoint: str = "",
    parse_priority_tiers: str = "1,2",
    skip_download: bool = False,
) -> dict:
    """Run Phase 1-5 end-to-end.

    Returns::

        {
            "company_name": str,
            "ingestion": {ingestion summary from run_ingestion_pipeline()},
            "diligence": {run manifest from run_pipeline()},
            "summary": {
                "ingestion": {"SUCCESS": int, "FAILED": int, "SKIPPED": int},
                "diligence": {"SUCCESS": int, "FAILED": int, "SKIPPED": int},
            },
        }
    """
    scripts_dir = _find_scripts_dir()
    repo_root   = _find_repo_root(scripts_dir)
    for p in (repo_root, scripts_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    # ── Phase 1-2: Ingestion ─────────────────────────────────────────────
    from run_ingestion_pipeline import run_ingestion_pipeline

    ingestion = run_ingestion_pipeline(
        company_name=company_name,
        catalog=catalog,
        schema=schema,
        embedding_endpoint=embedding_endpoint,
        vision_endpoint=vision_endpoint,
        parse_priority_tiers=parse_priority_tiers,
        skip_download=skip_download,
    )

    # Abort if critical Phase 2 steps failed — no embeddings means every
    # retrieval call in Phase 3 returns nothing and agents write empty rows.
    ing_phases    = ingestion.get("phases", {})
    classifier_ok = ing_phases.get("document_classifier", {}).get("status") in ("SUCCESS", "SKIPPED")
    parser_ok     = ing_phases.get("ingestion_parser",    {}).get("status") in ("SUCCESS", "SKIPPED")

    if not classifier_ok or not parser_ok:
        print(
            "\n[full_pipeline] Aborting Phase 3-5: ingestion did not populate embeddings. "
            "Fix the Phase 1-2 errors above and re-run."
        )
        return {
            "company_name": company_name,
            "ingestion":    ingestion,
            "diligence":    {
                "note": "skipped — ingestion did not complete (no embeddings)"
            },
            "summary": {
                "ingestion": ingestion["summary"],
                "diligence": {"SUCCESS": 0, "FAILED": 0, "SKIPPED": 9},
            },
        }

    if ing_phases.get("company_profiler", {}).get("status") == "FAILED":
        print(
            "\n[full_pipeline] company_profiler failed — Phase 3-5 will continue "
            "in degraded mode (overlay detection falls back to CIM heuristics)."
        )

    # ── Phase 3-5: Diligence ─────────────────────────────────────────────
    # Mirror diligence-specific params into os.environ.
    # run_ingestion_pipeline() already mirrored its own params.
    os.environ["llm_endpoint"]        = llm_endpoint
    os.environ["extraction_endpoint"] = extraction_endpoint

    from agents.orchestration.pipeline import run_pipeline

    diligence = run_pipeline(
        company_name=company_name,
        catalog=catalog,
        llm_endpoint=llm_endpoint,
        extraction_endpoint=extraction_endpoint,
        run_orchestrator=True,
    )

    return {
        "company_name":    company_name,
        "ingestion":       ingestion,
        "diligence":       diligence,
        "summary": {
            "ingestion": ingestion["summary"],
            "diligence": diligence.get("summary", {}),
        },
        "report_md_path":   diligence.get("report_md_path"),
        "report_docx_path": diligence.get("report_docx_path"),
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

    company_name         = _arg(0, "sp_company_name")
    catalog              = _arg(1, "catalog",              "uc13")
    schema               = _arg(2, "schema",               "ingestion")
    embedding_endpoint   = _arg(3, "embedding_endpoint",   "databricks-bge-large-en")
    llm_endpoint         = _arg(4, "llm_endpoint",         "databricks-claude-sonnet-4-6")
    extraction_endpoint  = _arg(5, "extraction_endpoint",  llm_endpoint)
    vision_endpoint      = _arg(6, "vision_endpoint",      "")
    parse_priority_tiers = _arg(7, "parse_priority_tiers", "1,2")

    if not company_name:
        raise RuntimeError(
            "sp_company_name is required (argv[0], widget, or env var sp_company_name)."
        )

    os.environ["sp_company_name"]      = company_name
    os.environ["catalog"]              = catalog
    os.environ["schema"]               = schema
    os.environ["embedding_endpoint"]   = embedding_endpoint
    os.environ["llm_endpoint"]         = llm_endpoint
    os.environ["extraction_endpoint"]  = extraction_endpoint
    os.environ["vision_endpoint"]      = vision_endpoint
    os.environ["parse_priority_tiers"] = parse_priority_tiers

    print(f"=== Full pipeline job: {company_name} (catalog={catalog}) ===")

    result = run_full_pipeline(
        company_name=company_name,
        catalog=catalog,
        schema=schema,
        embedding_endpoint=embedding_endpoint,
        llm_endpoint=llm_endpoint,
        extraction_endpoint=extraction_endpoint,
        vision_endpoint=vision_endpoint,
        parse_priority_tiers=parse_priority_tiers,
    )

    ing_ok = result["summary"]["ingestion"].get("SUCCESS", 0) > 0
    dil_ok = result["summary"]["diligence"].get("SUCCESS", 0) > 0
    if not ing_ok and not dil_ok:
        raise RuntimeError(
            f"Full pipeline: all steps failed in both phases. "
            f"Summary: {result['summary']}"
        )
    return result


if __name__ == "__main__":
    main()
