"""
run_vdr_rainmaker.py — CIM-first Rainmaker POC runner.

The one decision this job makes (plan docs/plans/CIM-first-rainmaker-template
/plan.md §4/§7/§8):

    IF a CIM (or, absent one, a `special_folder`) is found in the company's
       data room → scope ingestion to it, run the 7 workstream agents
       (Ruta 2), build the canonical bundle, and render the Rainmaker
       "Opportunity Summary" PDF.
    ELSE → no-op with a message. This POC does NOT fall back to the full
       pipeline — that gate (`preview_ready` + UI approval) is a post-POC
       item (plan §8), out of scope here.

This is a NEW, separate entry point — it does not modify and is not called
by `run_vdr_pipeline.py`, `run_full_pipeline.py`, or the existing VDR job
(617196299594076). It reuses `run_vdr_pipeline.py`'s Delta-table helpers by
import (read/update the VDR record) so that plumbing isn't duplicated.

Invocation (spark_python_task positional argv):
    run_vdr_rainmaker.py <tableName> <id> [special_folder]

Also callable as a Python function::

    from run_vdr_rainmaker import run_vdr_rainmaker
    result = run_vdr_rainmaker("rallyday_partners_llc.default.companies_vdr_history", 42)
"""

import inspect
import os
import shutil
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

# The CIM-first preview runs in its own catalog so a CIM-scoped ingestion
# never DELETEs/overwrites the company's full-room prod data in `uc13`
# (ingestion_parser.main() is DELETE-all-then-append per company_name) —
# plan §11.2, Apéndice A.5.
PREVIEW_CATALOG = "uc13_preview"


# ---------------------------------------------------------------------------
# Path helpers (same pattern as run_vdr_pipeline.py / run_full_pipeline.py)
# ---------------------------------------------------------------------------

def _find_scripts_dir() -> str:
    here = Path(inspect.getfile(_find_scripts_dir)).resolve().parent
    if (here / "run_vdr_pipeline.py").exists():
        return str(here)
    for start in (Path.cwd(), here):
        for c in [start, *start.parents]:
            s = c / "jobs" / "scripts"
            if (s / "run_vdr_pipeline.py").exists():
                return str(s)
    raise RuntimeError(
        "Cannot locate jobs/scripts directory (run_vdr_pipeline.py not found)."
    )


def _ensure_sys_path(scripts_dir: str) -> None:
    for p in (str(Path(scripts_dir).parent.parent), scripts_dir):
        if p not in sys.path:
            sys.path.insert(0, p)


def _detect_cim_files(company_name: str, special_folder: str) -> list[str]:
    """List the company's SharePoint files and run detect_cim() over them.

    Reuses download_upload.get_secret()/get_param() to inject the same
    SharePoint credentials download_upload.main() injects — no separate
    credential path is introduced.
    """
    import download_upload as du
    from agents.ingestion.tools.connector import list_files
    from cim_detection import detect_cim

    os.environ["SP_TENANT_ID"]     = du.get_secret("sp_tenant_id")
    os.environ["SP_CLIENT_ID"]     = du.get_secret("sp_client_id")
    os.environ["SP_CLIENT_SECRET"] = du.get_secret("sp_client_secret")
    os.environ["SP_SITE_URL"]      = du.get_secret("sp_site_url")
    os.environ["SP_FOLDER_PATH"]   = du.get_secret("sp_folder_path")
    os.environ["SP_COMPANY_NAME"]  = company_name

    connector = SimpleNamespace(list_files=list_files)
    return detect_cim(company_name, connector, special_folder=special_folder)


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

def run_vdr_rainmaker(
    table_name: str,
    record_id: int,
    special_folder: str = "",
) -> dict:
    """Run the CIM-first Rainmaker POC for one VDR record.

    Returns::

        {"status": "success", "company_name": ..., "cim_files": [...],
         "output_dir": ..., "files": [...]}
        # or, when no CIM is found:
        {"status": "skipped", "company_name": ..., "reason": "no_cim_found"}
    """
    scripts_dir = _find_scripts_dir()
    _ensure_sys_path(scripts_dir)

    from run_vdr_pipeline import (
        _build_output_dir,
        _find_repo_root,
        _get_spark,
        _now_iso,
        _read_vdr_record,
        _update_vdr_record,
    )

    spark = _get_spark()
    record = _read_vdr_record(spark, table_name, record_id)
    company_name = record["company_name"]
    if not company_name:
        raise ValueError(f"Record {record_id} has no company_name")

    print(f"=== VDR Rainmaker POC: {company_name} (id={record_id}) ===")

    _update_vdr_record(spark, table_name, record_id, {
        "processing_status": "processing",
        "updated_at":        _now_iso(),
        "last_updated_by":   "vdr-rainmaker-poc",
    })

    try:
        repo_root = _find_repo_root(scripts_dir)
        for p in (repo_root, scripts_dir):
            if p not in sys.path:
                sys.path.insert(0, p)

        cim_files = _detect_cim_files(company_name, special_folder)

        # ── The one decision this job makes: CIM found, or not. ──────────
        if not cim_files:
            note = "No CIM found in the data room; Rainmaker preview skipped."
            print(f"  {note}")
            _update_vdr_record(spark, table_name, record_id, {
                "processing_status": "done",
                "completion_status": "success",
                "error_message":     note,
                "updated_at":        _now_iso(),
                "last_updated_by":   "vdr-rainmaker-poc",
            })
            return {"status": "skipped", "company_name": company_name, "reason": "no_cim_found"}

        print(f"  CIM detected: {cim_files}")

        from agents.exec_summary.bundle_builder import BundleBuilder
        from agents.exec_summary.rainmaker_narrative import synthesize_rainmaker_narrative
        from agents.exec_summary.renderers import render_rainmaker
        from agents.exec_summary.validate import validate_bundle
        from agents.orchestration.pipeline import run_pipeline
        from agents.shared.agent_base import (
            get_token_totals,
            print_token_summary,
            reset_token_counter,
        )
        from run_ingestion_pipeline import run_ingestion_pipeline

        reset_token_counter()
        llm_endpoint    = os.environ.get("llm_endpoint", "databricks-claude-sonnet-4-6")
        vision_endpoint = os.environ.get("vision_endpoint", "databricks-claude-haiku-4-5")

        # Scoped ingestion: only the CIM (or special_folder files), in the
        # isolated preview catalog — never `uc13` (plan §11.2/Apéndice A.5).
        #
        # force="company": since Ale's M0-M4 merge, ParseManifest skips docs
        # already COMPLETE in doc_status, so the default force="none" would
        # make a re-preview of the same CIM a no-op ("No work items"). A
        # preview must be re-runnable on demand — an operator re-triggers it
        # after a template or agent change, with the same CIM. force is
        # per-doc (not a company-wide wipe), and this catalog only ever holds
        # whitelisted CIM docs, so the blast radius is exactly those files.
        run_ingestion_pipeline(
            company_name=company_name,
            catalog=PREVIEW_CATALOG,
            vision_endpoint=vision_endpoint,
            parse_priority_tiers="all",
            file_whitelist=cim_files,
            force="company",
        )

        # Ruta 2: the same 7 workstream agents + Cross-Analysis, scoped to
        # the CIM's chunks by virtue of the preview catalog's index only
        # containing them. run_orchestrator=False skips the Phase 5 memo —
        # this preview is one-pager only (plan §5.5).
        run_pipeline(
            company_name=company_name,
            catalog=PREVIEW_CATALOG,
            llm_endpoint=llm_endpoint,
            run_orchestrator=False,
        )

        bundle = BundleBuilder().build(company_name, PREVIEW_CATALOG, spark, llm_endpoint)
        validate_bundle(bundle)

        narrative = synthesize_rainmaker_narrative(bundle, llm_endpoint, spark)
        print(f"  Rainmaker narrative synthesis: {narrative.get('synthesis_status')}")

        rendered = render_rainmaker(bundle, PREVIEW_CATALOG, company_name, narrative=narrative)

        token_totals = get_token_totals()
        print_token_summary()

        # ── Copy outputs to the VDR volume ───────────────────────────────
        output_dir = _build_output_dir(company_name)
        spark.sql("CREATE VOLUME IF NOT EXISTS rallyday_partners_llc.default.vdr")
        os.makedirs(output_dir, exist_ok=True)

        files_copied = []
        pdf_src = rendered.get("pdf")
        if pdf_src and os.path.exists(pdf_src):
            dst = os.path.join(output_dir, "executive_summary.pdf")
            shutil.copy2(pdf_src, dst)
            files_copied.append(dst)
        html_src = rendered.get("html")
        if html_src and os.path.exists(html_src):
            dst = os.path.join(output_dir, "rainmaker_opportunity_summary.html")
            shutil.copy2(html_src, dst)
            files_copied.append(dst)

        if not files_copied:
            raise RuntimeError("render_rainmaker produced neither a PDF nor an HTML output")

        print(f"  Output files → {output_dir}")
        for f in files_copied:
            print(f"    · {f}")

        _update_vdr_record(spark, table_name, record_id, {
            "processing_status":  "done",
            "completion_status":  "success",
            "results_location":   output_dir + "/",
            "model_name":         llm_endpoint,
            "completion_tokens":  token_totals.get("completion_tokens", 0),
            "prompt_tokens":      token_totals.get("prompt_tokens", 0),
            "total_tokens":       token_totals.get("total_tokens", 0),
            "updated_at":         _now_iso(),
            "last_updated_by":    "vdr-rainmaker-poc",
        })

        print(f"\n=== VDR Rainmaker POC COMPLETE: {company_name} → {output_dir}/ ===")
        return {
            "status":       "success",
            "company_name": company_name,
            "cim_files":    cim_files,
            "output_dir":   output_dir,
            "files":        files_copied,
        }

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc(limit=6)
        print(f"\n=== VDR Rainmaker POC FAILED: {company_name} ===")
        print(f"  Error: {error_msg}")
        print(tb)

        try:
            _update_vdr_record(spark, table_name, record_id, {
                "processing_status":  "error",
                "completion_status":  "failure",
                "error_message":      error_msg[:4000],
                "updated_at":         _now_iso(),
                "last_updated_by":    "vdr-rainmaker-poc",
            })
        except Exception as update_exc:
            print(f"  [CRITICAL] Failed to update error status: {update_exc}")

        raise


# ---------------------------------------------------------------------------
# Job entry point
# ---------------------------------------------------------------------------

def main():
    argv = sys.argv[1:]

    def _arg(i, key, default=None):
        if i < len(argv) and argv[i]:
            return argv[i]
        return os.environ.get(key, default)

    table_name     = _arg(0, "tableName")
    record_id_str   = _arg(1, "id")
    special_folder  = _arg(2, "special_folder", "") or ""

    if not table_name:
        raise ValueError("table_name is required (argv[0] or 'tableName' env var)")
    if not record_id_str:
        raise ValueError("record_id is required (argv[1] or 'id' env var)")

    run_vdr_rainmaker(table_name, int(record_id_str), special_folder=special_folder)


if __name__ == "__main__":
    main()
