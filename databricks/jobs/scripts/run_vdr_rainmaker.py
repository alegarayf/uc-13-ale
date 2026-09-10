"""
run_vdr_rainmaker.py — unified VDR runner: CIM-scoped preview OR full-room
pipeline, always ending in the same Rainmaker-format executive review.

The one decision this job makes (plan docs/plans/connect-all-vdr-er.md §1/§5):

    IF a CIM (or, absent one, a `special_folder`) is found in the company's
       data room → scope ingestion to it, run the 7 workstream agents
       (Ruta 2), build the canonical bundle, and render the Rainmaker
       "Opportunity Summary" PDF.
    ELSE → run the full Phase 1-5 pipeline over the whole data room, then
       render the SAME Rainmaker-format executive review from the resulting
       bundle, plus ship the full diligence memo (`full_report.docx`).
       Pass `no_cim_mode="noop"` to restore the old message-only behavior
       instead (kill switch, not the default).

Both branches write to the SAME working catalog, `VDR_CATALOG` ("uc13_preview")
— see the plan §3 for why: it is the only catalog already prepared for the
M0-M4 schema, and it is proven end-to-end on a real run. Production `uc13`
stays frozen until a deliberate promotion step (plan Appendix A).

This entry point does not modify and is not called by `run_vdr_pipeline.py`
(the legacy standalone entry, still hardcoded to `uc13`) or the existing VDR
job's other notebook (`run_vdr_job`). It reuses `run_vdr_pipeline.py`'s
Delta-table helpers by import (read/update the VDR record) so that plumbing
isn't duplicated.

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

# ONE catalog for both modes (plan §3). Renamed from PREVIEW_CATALOG: it is
# no longer CIM-preview-only — the full-room path writes here too. Isolated
# from production `uc13`, which stays frozen until the plan's Appendix A
# promotion step. A CIM-scoped ingestion never DELETEs/overwrites a
# company's full-room data here either way (ingestion_parser.main() deletes
# per-doc, not per-company).
VDR_CATALOG = "uc13_preview"


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


class _SafeProgress:
    """Wraps a `vdr_progress.Progress` instance so a broken progress emitter
    can never fail the run. `Progress` already swallows its own exceptions
    (vdr_progress.py's own contract), but this runner does not rely on that
    alone — progress is never load-bearing here either (plan §6)."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def __getattr__(self, name):
        attr = getattr(self._inner, name)

        def _wrapped(*args, **kwargs):
            try:
                return attr(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - must never fail a diligence run
                print(f"[run_vdr_rainmaker] progress.{name} failed: {exc}")

        return _wrapped


def _run_final_report_stage(
    spark,
    table_name: str,
    record_id: int,
    company_name: str,
    output_dir: str,
    progress,
    run_mode: str,
    run_ingest: bool,
    run_agents: bool,
    prior_run_modes: tuple,
    rescore_mps: bool,
    llm_endpoint: str,
    vision_endpoint: str,
) -> dict:
    """Stage 2: full-room ingestion (Branch A only) → agents → final report.

    Never raises: the executive review is already delivered by the time this
    runs, and a stage-2 failure must leave it intact. Returns
    {"status": "success"|"failed", "stage": str|None, "error": str|None,
     "files": [...]}.
    """
    from run_ingestion_pipeline import run_ingestion_pipeline
    from agents.orchestration.pipeline import run_pipeline
    from agents.exec_summary.final_report_entry import (
        _load_prior_mps_runs,
        build_final_report,
    )

    current_stage = None
    try:
        if rescore_mps and not (run_ingest or run_agents):
            # A programming error in the caller, not a runtime condition —
            # this one *may* raise; caught by this function's own except
            # below like any other stage-2 failure.
            raise ValueError(
                "rescore_mps=True requires run_ingest or run_agents — "
                "re-scoring is only meaningful when stage 2 actually read "
                "something new"
            )

        if run_ingest:
            current_stage = "vdr_ingestion"
            progress.start("vdr_ingestion")
            ingestion = run_ingestion_pipeline(
                company_name=company_name,
                catalog=VDR_CATALOG,
                vision_endpoint=vision_endpoint,
                parse_priority_tiers="1,2",
            )
            parse_phase = ingestion["phases"].get("ingestion_parser", {})
            if parse_phase.get("status") != "SUCCESS":
                msg = (
                    "Stage-2 ingestion did not complete — refusing to build the "
                    "final report on stale chunks. Phase statuses: "
                    + ", ".join(
                        f"{name}={info.get('status')}"
                        + (f" ({info['error']})" if info.get("error") else "")
                        for name, info in ingestion["phases"].items()
                    )
                )
                progress.fail("vdr_ingestion", msg)
                return {"status": "failed", "stage": "vdr_ingestion", "error": msg, "files": []}
            progress.complete("vdr_ingestion")

        if run_agents:
            current_stage = "vdr_agents"
            progress.start("vdr_agents")
            run_pipeline(
                company_name=company_name,
                catalog=VDR_CATALOG,
                llm_endpoint=llm_endpoint,
                run_orchestrator=False,
            )
            progress.complete("vdr_agents")

        current_stage = "final_report"
        progress.start("final_report")

        prior = (
            _load_prior_mps_runs(spark, VDR_CATALOG, company_name, prior_run_modes)
            if prior_run_modes
            else []
        )

        # D-02 (plan §3): when stage 2 read no new evidence — Branch B, where
        # the ER already scored THIS bundle — reuse the ER's run instead of
        # paying for a second score over identical data.
        reuse = None
        if not rescore_mps:
            existing = _load_prior_mps_runs(spark, VDR_CATALOG, company_name, (run_mode,))
            reuse = existing[-1] if existing else None

        built = build_final_report(
            company_name, VDR_CATALOG, spark, llm_endpoint,
            run_mode=run_mode, prior_mps_runs=prior or None, reuse_mps_run=reuse,
        )
        print(f"  Final report MPS source: {built.get('mps_source')}")

        files_copied = []
        pdf_src = built.get("pdf")
        if pdf_src and os.path.exists(pdf_src):
            dst = os.path.join(output_dir, "full_report.pdf")
            shutil.copy2(pdf_src, dst)
            files_copied.append(dst)
        html_src = built.get("html")
        if html_src and os.path.exists(html_src):
            dst = os.path.join(output_dir, "full_report.html")
            shutil.copy2(html_src, dst)
            files_copied.append(dst)

        if not files_copied:
            msg = f"Final report produced neither a PDF nor an HTML output (status={built.get('status')})"
            progress.fail("final_report", msg)
            return {"status": "failed", "stage": "final_report", "error": msg, "files": []}

        if built.get("pdf_degraded"):
            print("  [WARNING] Final report PDF is degraded; HTML delivery still intact.")

        progress.complete("final_report", artifacts=files_copied)
        progress.complete("final_report_ready", artifacts=files_copied)

        return {"status": "success", "stage": None, "error": None, "files": files_copied}

    except Exception as exc:  # noqa: BLE001 - stage 2 must never fail the run
        msg = f"{type(exc).__name__}: {exc}"
        print(f"  [stage2] {current_stage} failed: {msg}")
        if current_stage is not None:
            progress.fail(current_stage, msg)
        return {"status": "failed", "stage": current_stage, "error": msg, "files": []}


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
# No-CIM branch — full-room pipeline + the same Rainmaker executive review
# ---------------------------------------------------------------------------

def _run_full_room_flow(spark, table_name: str, record_id: int, company_name: str) -> dict:
    """Run the full Phase 1-5 pipeline over the whole data room, then build
    the same Rainmaker-format executive review the CIM branch builds, then
    continue into the final-report stage 2 (§2 Branch B of the plan).

    Ships three files: `executive_summary.pdf` (Rainmaker ER), the html
    render, and `full_report.docx` (the orchestrator memo). The Rev3 Word
    one-pager (`tldr_docx`) that `run_full_pipeline` also produces is
    intentionally NOT copied into the VDR delivery folder (Hector,
    2026-08-11) — see the commented-out copy below. It is still generated
    on disk by `run_full_pipeline`'s own `build_exec_summary` call; nothing
    is lost, it just isn't part of this delivery.
    """
    from run_vdr_pipeline import _build_output_dir, _now_iso, _update_vdr_record
    from vdr_progress import STAGES_FULL, Progress

    from agents.exec_summary.rainmaker_entry import build_rainmaker_summary
    from agents.shared.agent_base import (
        get_token_totals,
        print_token_summary,
        reset_token_counter,
    )
    from run_full_pipeline import run_full_pipeline

    print("  No CIM found — running the full Phase 1-5 pipeline on "
          f"{VDR_CATALOG}.")

    os.environ["sp_company_name"] = company_name
    reset_token_counter()
    llm_endpoint    = os.environ.get("llm_endpoint", "databricks-claude-sonnet-4-6")
    vision_endpoint = os.environ.get("vision_endpoint", "databricks-claude-haiku-4-5")

    # A fresh Progress, not the caller's STAGES_CIM one — Branch B's stage
    # vocabulary collapses ingestion+agents into one `vdr_pipeline` stage
    # (plan §4), which STAGES_CIM does not have a key for.
    # Explicit updater=_update_vdr_record — the name this module just
    # resolved via its own local import — rather than vdr_progress's default
    # (its own top-level import, captured once at first module load, which
    # would not pick up a caller's monkeypatch of run_vdr_pipeline's).
    progress = _SafeProgress(Progress(spark, table_name, record_id, STAGES_FULL, updater=_update_vdr_record))
    progress.start("vdr_scan")      # the detect_cim call that returned []
    progress.complete("vdr_scan")

    # No `force`, no `file_whitelist` — the full-room path keeps M0's
    # incremental default so an unchanged doc is skipped. `force="company"`
    # is CIM-branch-only (a preview must be re-runnable on demand).
    progress.start("vdr_pipeline")
    result = run_full_pipeline(
        company_name=company_name,
        catalog=VDR_CATALOG,
        llm_endpoint=llm_endpoint,
        vision_endpoint=vision_endpoint,
    )

    # Same hollow-success class of bug as the CIM branch (session_log §9):
    # run_full_pipeline's own `parser_ok` guard accepts "SKIPPED" as well as
    # "SUCCESS" — not strict enough here. Require SUCCESS explicitly.
    ing_phases = result.get("ingestion", {}).get("phases", {})
    parse_phase = ing_phases.get("ingestion_parser", {})
    if parse_phase.get("status") != "SUCCESS":
        raise RuntimeError(
            "Full-room ingestion did not complete — refusing to build a "
            "report on stale/absent chunks. Phase statuses: "
            + ", ".join(
                f"{name}={info.get('status')}"
                + (f" ({info['error']})" if info.get("error") else "")
                for name, info in ing_phases.items()
            )
        )

    diligence = result.get("diligence", {})
    dil_summary = result.get("summary", {}).get("diligence", {})
    aborted = isinstance(diligence, dict) and "note" in diligence
    if aborted or dil_summary.get("SUCCESS", 0) == 0:
        raise RuntimeError(
            "Full-room diligence produced no successful agents — refusing "
            f"to build a report. Summary: {result.get('summary')}"
        )

    progress.complete("vdr_pipeline")
    progress.start("executive_review_ready")

    rendered = build_rainmaker_summary(
        company_name, VDR_CATALOG, spark, llm_endpoint, run_mode="full_vdr_no_cim"
    )
    print(f"  Rainmaker narrative synthesis: {rendered.get('synthesis_status')}")

    token_totals = get_token_totals()
    print_token_summary()

    # ── Copy outputs to the VDR volume ───────────────────────────────────
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
    report_docx = result.get("report_docx_path")
    # full_report.docx (the Phase-5 orchestrator memo) is temporarily NOT
    # shipped: the stage-2 final diligence report now delivers under that
    # base name, and the UI resolves a run's report by name alone. Two
    # different documents sharing "full_report" would be ambiguous to it.
    # The memo is still generated and still on disk at report_docx_path —
    # only the copy into the delivery folder is suspended. Re-enable by
    # uncommenting, and give one of the two documents a distinct name first.
    # if report_docx and os.path.exists(report_docx):
    #     dst = os.path.join(output_dir, "full_report.docx")
    #     shutil.copy2(report_docx, dst)
    #     files_copied.append(dst)

    # executive_summary.docx (the Rev3 prose one-pager) is intentionally NOT
    # shipped in the VDR delivery folder — the PDF above is the executive
    # review. Re-enable if a Word executive summary is wanted again; the
    # file is already on disk via run_full_pipeline's build_exec_summary.
    # tldr_docx = result.get("tldr_docx_path")
    # if tldr_docx and os.path.exists(tldr_docx):
    #     dst = os.path.join(output_dir, "executive_summary.docx")
    #     shutil.copy2(tldr_docx, dst)
    #     files_copied.append(dst)

    if not (pdf_src and os.path.exists(pdf_src)) and not (
        report_docx and os.path.exists(report_docx)
    ):
        raise RuntimeError(
            "Neither the Rainmaker PDF nor full_report.docx were produced"
        )

    print(f"  Output files → {output_dir}")
    for f in files_copied:
        print(f"    · {f}")

    progress.complete("executive_review_ready", artifacts=files_copied)
    # Published EARLY, before stage 2 starts — the deal team can download the
    # executive review while the final report is still being built. The
    # terminal update below sets it again, harmlessly.
    progress.publish({"results_location": output_dir + "/"})

    # ── STAGE 2 — the final report. Cannot fail the run (plan §6). ─────────
    # The room is already ingested and the agents have already run inside
    # run_full_pipeline(); the ER already scored this exact bundle, so the
    # MPS run is reused, not re-scored (D-02, plan §3).
    stage2 = _run_final_report_stage(
        spark, table_name, record_id, company_name, output_dir, progress,
        run_mode="full_vdr_no_cim", run_ingest=False, run_agents=False,
        prior_run_modes=(), rescore_mps=False,
        llm_endpoint=llm_endpoint, vision_endpoint=vision_endpoint,
    )
    if stage2["status"] == "success":
        files_copied = files_copied + stage2["files"]

    completion_status = "success"
    error_message = None
    if stage2["status"] != "success":
        # A-1 (plan §6): the live table has no CHECK constraint on
        # completion_status, but the only values it has ever held are
        # "success"/"failure" and the column comment documents exactly that
        # vocabulary. "partial" is not used — the failed stage is visible in
        # progress_json instead.
        error_message = (stage2["error"] or "final report stage failed")[:4000]

    _update_vdr_record(spark, table_name, record_id, {
        "processing_status":  "done",
        "completion_status":  completion_status,
        "results_location":   output_dir + "/",
        "error_message":      error_message,
        "model_name":         llm_endpoint,
        "completion_tokens":  token_totals.get("completion_tokens", 0),
        "prompt_tokens":      token_totals.get("prompt_tokens", 0),
        "total_tokens":       token_totals.get("total_tokens", 0),
        "updated_at":         _now_iso(),
        "last_updated_by":    "vdr-backend-ai",
    })

    print(f"\n=== VDR Rainmaker (full-room) COMPLETE: {company_name} → {output_dir}/ ===")
    return {
        "status":       "success",
        "mode":         "full_pipeline",
        "company_name": company_name,
        "cim_files":    [],
        "output_dir":   output_dir,
        "files":        files_copied,
    }


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

def run_vdr_rainmaker(
    table_name: str,
    record_id: int,
    special_folder: str = "",
    no_cim_mode: str = "full",
) -> dict:
    """Run the unified VDR flow for one record.

    `no_cim_mode`: what to do when no CIM is found — "full" (default) runs
    the full Phase 1-5 pipeline and renders the same Rainmaker executive
    review; "noop" is a kill switch that restores the old message-only
    behavior without a code change.

    Returns::

        {"status": "success", "mode": "cim_preview"|"full_pipeline",
         "company_name": ..., "cim_files": [...], "output_dir": ...,
         "files": [...]}
        # or, when no CIM is found and no_cim_mode="noop":
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
    from vdr_progress import STAGES_CIM, Progress, ensure_progress_columns

    spark = _get_spark()
    record = _read_vdr_record(spark, table_name, record_id)
    company_name = record["company_name"]
    if not company_name:
        raise ValueError(f"Record {record_id} has no company_name")

    print(f"=== VDR Rainmaker: {company_name} (id={record_id}) ===")

    ensure_progress_columns(spark, table_name)

    _update_vdr_record(spark, table_name, record_id, {
        "processing_status": "processing",
        "updated_at":        _now_iso(),
        "last_updated_by":   "vdr-rainmaker-poc",
    })

    # See _run_full_room_flow's comment: explicit updater, not vdr_progress's
    # own captured default, so a caller's monkeypatch of
    # run_vdr_pipeline._update_vdr_record is honored.
    progress = _SafeProgress(Progress(spark, table_name, record_id, STAGES_CIM, updater=_update_vdr_record))

    try:
        repo_root = _find_repo_root(scripts_dir)
        for p in (repo_root, scripts_dir):
            if p not in sys.path:
                sys.path.insert(0, p)

        progress.start("cim_detection")
        cim_files = _detect_cim_files(company_name, special_folder)
        progress.complete("cim_detection", {"cim_files": cim_files})

        # ── The one decision this job makes: CIM found, or not. ──────────
        if not cim_files:
            if no_cim_mode == "noop":
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

            return _run_full_room_flow(spark, table_name, record_id, company_name)

        print(f"  CIM detected: {cim_files}")

        from agents.exec_summary.rainmaker_entry import build_rainmaker_summary
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
        # isolated preview catalog — never `uc13`.
        #
        # force="company": since Ale's M0-M4 merge, ParseManifest skips docs
        # already COMPLETE in doc_status, so the default force="none" would
        # make a re-preview of the same CIM a no-op ("No work items"). A
        # preview must be re-runnable on demand — an operator re-triggers it
        # after a template or agent change, with the same CIM. force is
        # per-doc (not a company-wide wipe), and this catalog only ever holds
        # whitelisted CIM docs, so the blast radius is exactly those files.
        progress.start("cim_ingestion")
        ingestion = run_ingestion_pipeline(
            company_name=company_name,
            catalog=VDR_CATALOG,
            vision_endpoint=vision_endpoint,
            parse_priority_tiers="all",
            file_whitelist=cim_files,
            force="company",
        )

        # run_ingestion_pipeline reports per-phase status in its return value and
        # does NOT raise — only its CLI main() maps failure to a non-zero exit.
        # Called programmatically, a failed parse therefore used to pass silently:
        # the agents below would run against whatever chunks the catalog already
        # held, and the job reported SUCCESS on a PDF built from stale data. That
        # really happened (run 572985817765568: the parse failed on
        # WRONG_COLUMN_DEFAULTS_FOR_DELTA_FEATURE_NOT_ENABLED, the agents scored
        # 3-day-old chunks, and record 47 flipped to done/success). Fail loudly
        # instead — a preview built on unknown-age chunks is worse than no
        # preview, because nothing downstream reveals which one it was.
        parse_phase = ingestion["phases"].get("ingestion_parser", {})
        if parse_phase.get("status") != "SUCCESS":
            raise RuntimeError(
                "Scoped ingestion did not complete — refusing to build a preview "
                "on stale chunks. Phase statuses: "
                + ", ".join(
                    f"{name}={info.get('status')}"
                    + (f" ({info['error']})" if info.get("error") else "")
                    for name, info in ingestion["phases"].items()
                )
            )
        progress.complete("cim_ingestion")

        # Ruta 2: the same 7 workstream agents + Cross-Analysis, scoped to
        # the CIM's chunks by virtue of the preview catalog's index only
        # containing them. run_orchestrator=False skips the Phase 5 memo —
        # this preview is one-pager only.
        progress.start("cim_agents")
        run_pipeline(
            company_name=company_name,
            catalog=VDR_CATALOG,
            llm_endpoint=llm_endpoint,
            run_orchestrator=False,
        )
        progress.complete("cim_agents")

        progress.start("executive_review_ready")
        rendered = build_rainmaker_summary(
            company_name, VDR_CATALOG, spark, llm_endpoint, run_mode="cim_only"
        )
        print(f"  Rainmaker narrative synthesis: {rendered.get('synthesis_status')}")

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

        progress.complete("executive_review_ready", artifacts=files_copied)
        # Published EARLY, before stage 2 starts — the deal team can
        # download the executive review while the final report is still
        # being built. The terminal update below sets it again, harmlessly.
        progress.publish({"results_location": output_dir + "/"})

        # ── STAGE 2 — the final report. New. Cannot fail the run (plan §6). ──
        stage2 = _run_final_report_stage(
            spark, table_name, record_id, company_name, output_dir, progress,
            run_mode="full_vdr_after_cim", run_ingest=True, run_agents=True,
            prior_run_modes=("cim_only",), rescore_mps=True,
            llm_endpoint=llm_endpoint, vision_endpoint=vision_endpoint,
        )
        if stage2["status"] == "success":
            files_copied = files_copied + stage2["files"]

        completion_status = "success"
        error_message = None
        if stage2["status"] != "success":
            # A-1 (plan §6): the live table has no CHECK constraint on
            # completion_status, but the only values it has ever held are
            # "success"/"failure" and the column comment documents exactly
            # that vocabulary. "partial" is not used — the failed stage is
            # visible in progress_json instead.
            error_message = (stage2["error"] or "final report stage failed")[:4000]

        _update_vdr_record(spark, table_name, record_id, {
            "processing_status":  "done",
            "completion_status":  completion_status,
            "results_location":   output_dir + "/",
            "error_message":      error_message,
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
            "mode":         "cim_preview",
            "company_name": company_name,
            "cim_files":    cim_files,
            "output_dir":   output_dir,
            "files":        files_copied,
        }

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc(limit=6)
        print(f"\n=== VDR Rainmaker FAILED: {company_name} ===")
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
    no_cim_mode     = _arg(3, "no_cim_mode", "full") or "full"

    if not table_name:
        raise ValueError("table_name is required (argv[0] or 'tableName' env var)")
    if not record_id_str:
        raise ValueError("record_id is required (argv[1] or 'id' env var)")

    run_vdr_rainmaker(
        table_name, int(record_id_str), special_folder=special_folder, no_cim_mode=no_cim_mode,
    )


if __name__ == "__main__":
    main()
