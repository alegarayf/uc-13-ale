"""
orchestrator_agent.py — Phase 5: Orchestrator Agent (Spec §11, Guideline 9).

The Orchestrator is the only agent whose primary job is OUTPUT GENERATION. It takes
the structured outputs of all prior agents and assembles the final diligence memo.

Per the agreed scope, this build produces ONLY the diligence memo as Markdown +
Word (.docx). The other §11.2 deliverables (executive deck, one-pager PDF, KPI
dashboard, etc.) are intentionally out of scope — the ``diligence_report`` schema
leaves an extensible ``deliverables_json`` hook so they can be added later without
a migration.

Context discipline: the memo is ASSEMBLED, not summarized in one giant prompt.
  - The per-section narratives are produced by each workstream agent's own
    ``generate_*_assessment()`` function, each reading ONLY its own Delta row —
    so no single LLM call ever sees all seven workstreams at once.
  - The executive summary is the only cross-cutting LLM call, and it is fed a
    COMPACT digest (result cards + ratings grid + top-10), never the full memo.
  - Coherence validation (§11.1) and section confidence (§11.3) are DETERMINISTIC.
  - A workstream agent that FAILED or was SKIPPED renders as
    "section not available" rather than breaking the memo.

Phase 5 outputs:
  - Table  uc13.analysis.diligence_report
  - Files  /Volumes/{catalog}/analysis/reports/{company}/final_diligence_memo_{company}.md
           /Volumes/{catalog}/analysis/reports/{company}/final_diligence_memo_{company}.docx
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _fmt_manifest_md(manifest: dict) -> str:
    """Format the agent run manifest as a readable markdown table instead of raw JSON."""
    if not manifest or "note" in manifest:
        return f"_{manifest.get('note', 'No manifest available.')}_"

    summary   = manifest.get("summary", {})
    runs      = manifest.get("runs", [])
    generated = manifest.get("generated_at", "")

    _status_emoji = {"SUCCESS": "✅", "FAILED": "❌", "SKIPPED": "⏭", "RUNNING": "🔄"}

    header = (
        f"**Generated:** {generated}  ·  "
        f"**✅ SUCCESS:** {summary.get('SUCCESS', 0)}  ·  "
        f"**❌ FAILED:** {summary.get('FAILED', 0)}  ·  "
        f"**⏭ SKIPPED:** {summary.get('SKIPPED', 0)}"
    )
    rows = ["| Agent | Status | Duration | Attempts | Degraded from | Error |",
            "|---|---|---|---|---|---|"]
    for r in runs:
        status   = r.get("status", "—")
        emoji    = _status_emoji.get(status, "")
        dur      = f"{r.get('duration_s')}s" if r.get("duration_s") else "—"
        degraded = ", ".join(r.get("degraded_from") or []) or "—"
        error    = (r.get("error") or "—")
        rows.append(
            f"| {r.get('agent', '—')} | {emoji} {status} | {dur} "
            f"| {r.get('attempts', '—')} | {degraded} | {error} |"
        )
    return header + "\n\n" + "\n".join(rows)


# ---------------------------------------------------------------------------
# Params / repo-root helpers
# ---------------------------------------------------------------------------

def _get_dbutils():
    try:
        return dbutils  # noqa: F821
    except NameError:
        pass
    try:
        import IPython
        user_ns = IPython.get_ipython().user_ns
        if "dbutils" in user_ns:
            return user_ns["dbutils"]
    except Exception:
        pass
    return None


def _load_dotenv_if_local():
    if _get_dbutils() is None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

_load_dotenv_if_local()


def get_param(key: str, default: str = None) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            value = _dbutils.widgets.get(key)
            if value:
                return value
        except Exception:
            pass
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(f"Parameter '{key}' not found.")
    return value


def get_current_path():
    try:
        notebook_path = (
            dbutils.notebook.entry_point  # noqa: F821
            .getDbutils().notebook().getContext().notebookPath().get()
        )
        return Path("/Workspace") / notebook_path.lstrip("/")
    except Exception:
        return Path(os.getcwd())


def find_repo_root(marker="agents"):
    current_path = get_current_path()
    if current_path.is_file():
        current_path = current_path.parent
    for path in [current_path, *current_path.parents]:
        if (path / marker).exists():
            return str(path)
    raise RuntimeError(f"Could not find a parent directory containing '{marker}'")


def _load_convert_md_to_word():
    """Import convert_md_to_word robustly across notebook / module contexts."""
    try:
        from jobs.scripts.md_to_word import convert_md_to_word
        return convert_md_to_word
    except Exception:
        pass
    try:
        import md_to_word  # SCRIPTS dir on sys.path (notebook convention)
        return md_to_word.convert_md_to_word
    except Exception:
        root = find_repo_root()
        sp = os.path.join(root, "jobs", "scripts")
        if sp not in sys.path:
            sys.path.insert(0, sp)
        import md_to_word
        return md_to_word.convert_md_to_word


# ---------------------------------------------------------------------------
# Section registry — order matches the memo structure (spec §11.2)
# ---------------------------------------------------------------------------

# (section_no, title, agent_key, table, module_path, generator_fn_name)
# generator_fn_name=None → deterministic fallback section (Legal has no generator).
_SECTIONS = [
    (1, "Business Model",      "business_model",      "business_model",
     "agents.workstreams.business_model_agent",     "generate_business_model_assessment"),
    (2, "Financial Trends",    "financial_trends",    "financial_trends",
     "agents.workstreams.financial_trends_agent",   "generate_financial_assessment"),
    (3, "Customer Quality",    "customer_quality",    "customer_quality",
     "agents.workstreams.customer_quality_agent",   "generate_customer_quality_assessment"),
    (4, "KPIs",                "kpi",                 "kpi",
     "agents.workstreams.kpi_agent",                "generate_kpi_assessment"),
    (5, "Legal & Contracts",   "legal_contracts",     "legal_contracts",
     "agents.workstreams.legal_contracts_agent",    None),
    (6, "Quality of Earnings", "quality_of_earnings", "quality_of_earnings",
     "agents.workstreams.quality_of_earnings_agent", "generate_qoe_assessment"),
    (7, "Forecast",            "forecast",            "forecast",
     "agents.workstreams.forecast_agent",           "generate_forecast_assessment"),
]


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

from agents.shared.agent_base import WorkstreamAgent


class OrchestratorAgent(WorkstreamAgent):
    """Phase 5 Orchestrator — assembles the final diligence memo (spec §11)."""

    agent_name = "orchestrator"

    def __init__(self):
        super().__init__()
        self._catalog = "uc13"

    # -- Delta reads (compact columns only) ------------------------------
    @staticmethod
    def _sanitize_row(row: dict) -> dict:
        """Convert non-JSON-serializable values (datetime, Decimal, …) to strings."""
        return {k: v.isoformat() if hasattr(v, "isoformat") else v
                for k, v in row.items()}

    def _load_row(self, table: str, company_name: str, spark) -> dict:
        try:
            rows = spark.sql(
                f"SELECT * FROM {self._catalog}.analysis.{table} WHERE company_name = :c "
                "ORDER BY created_at DESC LIMIT 1",
                args={"c": company_name},
            ).collect()
            return self._sanitize_row(rows[0].asDict()) if rows else {}
        except Exception:
            return {}

    @staticmethod
    def _jload(raw, default):
        if not raw:
            return default
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return default

    # -- §11.3 Section-level confidence (deterministic) ------------------
    def _section_confidence(self, card: Optional[dict], non_banked: bool) -> str:
        """High / Medium / Low per spec §11.3.

        - Low  : agent absent/failed OR data missing (gaps present and no citations).
        - High : present, has corroborating flags/citations, no material gaps.
        - Medium: single-source / CIM-only / partial corroboration.
        Non-banked deals are capped at Medium until financials are confirmed.
        """
        if not card or not card.get("present"):
            return "Low"
        gaps = card.get("data_room_gaps") or []
        flag_conf = [str(f.get("confidence", "")).lower() for f in card.get("flags", [])]
        high_conf = flag_conf and all(c == "high" for c in flag_conf)
        if not gaps and high_conf:
            base = "High"
        elif gaps and not flag_conf:
            base = "Low"
        else:
            base = "Medium"
        if non_banked and base == "High":
            return "Medium"
        return base

    def _is_non_banked(self, company_name: str, spark) -> bool:
        row = self._load_row_from("classification", "company_profile", company_name, spark)
        blob = json.dumps(row).lower()
        return "non-banked" in blob or "non banked" in blob or '"banked":"false"' in blob

    def _load_row_from(self, schema: str, table: str, company_name: str, spark) -> dict:
        try:
            rows = spark.sql(
                f"SELECT * FROM {self._catalog}.{schema}.{table} WHERE company_name = :c "
                "ORDER BY created_at DESC LIMIT 1",
                args={"c": company_name},
            ).collect()
            return self._sanitize_row(rows[0].asDict()) if rows else {}
        except Exception:
            return {}

    # -- §11.1 Coherence validation (deterministic) ----------------------
    def _coherence_check(self, cards: dict, cross_row: dict, confidences: dict,
                         company_name: str, spark) -> list:
        log = []
        top10 = self._jload(cross_row.get("top_10_issues_json"), [])
        top10_blob = json.dumps(top10).lower()

        # Rule 1 — every Red-rated workstream must surface in the top 10.
        for key, card in cards.items():
            if card.get("present") and card.get("rating") == "Red":
                surfaced = any(key in [w.lower() for w in i.get("workstreams", [])]
                               or key.replace("_", " ") in top10_blob for i in top10)
                log.append({
                    "rule": "Red flag reflected in top 10 issues",
                    "workstream": key,
                    "status": "ok" if surfaced else "violation",
                    "detail": ("Red-rated workstream present in top 10."
                               if surfaced else
                               f"Red-rated workstream '{key}' is NOT in the top 10 — reconcile."),
                })

        # Rule 2 — a Legal change-of-control issue must appear in the top 10.
        legal = cards.get("legal_contracts", {})
        if legal.get("present") and (legal.get("key_metrics", {}).get("coc_consent_items") or 0) > 0:
            coc_surfaced = any(k in top10_blob for k in ("change of control", "change-of-control",
                                                         "coc", "consent"))
            log.append({
                "rule": "Change-of-control issue reflected in top 10",
                "workstream": "legal_contracts",
                "status": "ok" if coc_surfaced else "violation",
                "detail": ("CoC item surfaced in top 10." if coc_surfaced else
                           "Legal flagged CoC consent items but none appear in the top 10."),
            })

        # Rule 3 — no section may claim High confidence when its agent logged data gaps.
        for key, conf in confidences.items():
            card = cards.get(key, {})
            if conf == "High" and (card.get("data_room_gaps") or []):
                log.append({
                    "rule": "Confidence consistent with source availability",
                    "workstream": key,
                    "status": "violation",
                    "detail": f"Section '{key}' rated High but logged data-room gaps — downgrade review.",
                })

        # Rule 4 — every cited document must resolve to an indexed source.
        try:
            idx_rows = spark.sql(
                f"SELECT DISTINCT file_name FROM {self._catalog}.ingestion.embeddings "
                "WHERE company_name = :c", args={"c": company_name}).collect()
            indexed = {r["file_name"] for r in idx_rows}
        except Exception:
            indexed = set()
        cited = set()
        for c in self._jload(cross_row.get("citations"), []):
            if c.get("document"):
                cited.add(c["document"])
        unresolved = [d for d in cited if indexed and d not in indexed
                      and not any(d in f or f in d for f in indexed)]
        log.append({
            "rule": "Source citations resolve to indexed documents",
            "workstream": "cross_analysis",
            "status": "ok" if not unresolved else "violation",
            "detail": ("All cross-analysis citations resolve." if not unresolved
                       else f"Unresolved citations: {unresolved[:5]}"),
        })
        return log

    # -- Section narrative assembly --------------------------------------
    def _legal_section_md(self, row: dict) -> str:
        contracts = self._jload(row.get("contract_register_json"), [])
        coc = self._jload(row.get("coc_consent_list_json"), [])
        litigation = self._jload(row.get("litigation_register_json"), [])
        flags = self._jload(row.get("flags"), [])
        md = [row.get("executive_summary") or "", ""]
        md.append(f"**Contracts reviewed:** {len(contracts)}  ·  "
                  f"**Change-of-control / consent items:** {len(coc)}  ·  "
                  f"**Open litigation items:** {len(litigation)}\n")
        if coc:
            md.append("**Change-of-control / consent required:**\n")
            for c in coc[:15]:
                md.append(f"- {c.get('counterparty', c.get('contract', ''))}: "
                          f"{c.get('clause', c.get('note',''))}")
            md.append("")
        if litigation:
            md.append("**Litigation register:**\n")
            for l in litigation[:15]:
                md.append(f"- {l.get('matter', l.get('description',''))} — "
                          f"{l.get('status','')}")
            md.append("")
        if flags:
            md.append("**Flags:**\n")
            md.append("| Severity | Metric | Note |")
            md.append("|---|---|---|")
            for f in flags:
                md.append(f"| {f.get('severity','')} | {f.get('metric','')} | {f.get('note','')} |")
        return "\n".join(md)

    def _fallback_section_md(self, key: str, card: Optional[dict]) -> str:
        if not card or not card.get("present"):
            return (f"_Section not available — the {key.replace('_',' ')} agent produced no output "
                    f"(agent failed after retries or was skipped). See the agent run manifest in the "
                    f"appendix._")
        md = [card.get("headline", ""), ""]
        flags = card.get("flags", [])
        if flags:
            md.append("| Severity | Metric | Value | Note |")
            md.append("|---|---|---|---|")
            for f in flags:
                md.append(f"| {f.get('severity','')} | {f.get('metric','')} | "
                          f"{f.get('value','')} | {f.get('note','')} |")
        return "\n".join(md)

    def _section_narrative(self, section, company_name, spark, llm_endpoint, card) -> str:
        _no, _title, key, table, module_path, gen_fn = section
        row = self._load_row(table, company_name, spark)
        if not row:
            return self._fallback_section_md(key, card)
        if gen_fn is None:  # Legal — deterministic
            try:
                return self._legal_section_md(row)
            except Exception as e:
                return self._fallback_section_md(key, card) + f"\n\n_(legal render error: {e})_"
        try:
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, gen_fn)
            # Each generator reads ONLY its own row → bounded context per call.
            return fn(row, spark, llm_endpoint, catalog=self._catalog, write_to_volume=False)
        except Exception as e:
            print(f"  [orchestrator] section '{key}' generator failed ({e}); using fallback.")
            return self._fallback_section_md(key, card)

    # -- Executive summary (the one cross-cutting LLM call) --------------
    def _exec_summary(self, cards, confidences, cross_row, llm_endpoint) -> str:
        digest = {
            "ratings": {k: {"rating": v.get("rating"), "confidence": confidences.get(k)}
                        for k, v in cards.items()},
            "headlines": {k: (v.get("headline") or "")[:250] for k, v in cards.items()
                          if v.get("present")},
            "top_10_issues": self._jload(cross_row.get("top_10_issues_json"), [])[:10],
            "reconciliation": self._jload(cross_row.get("reconciliation_summary_json"), {}),
        }
        system = (
            "You are the lead PE analyst writing the executive summary of a diligence memo "
            "for the investment committee. Be factual and neutral — do not render a "
            "buy/no-buy verdict. 3–4 short paragraphs: (1) what the business is and how it "
            "makes money; (2) the financial picture and quality of earnings; (3) the top "
            "risks/red flags from the top-10 list; (4) confidence and key open items. "
            "Reference workstreams by name. Do not invent numbers not in the digest."
        )
        user = ("Compact diligence digest (ratings, section headlines, top-10 issues, "
                "reconciliation summary):\n\n" + json.dumps(digest, indent=2)[:14000])
        try:
            return self._call_llm(system, user, llm_endpoint, max_tokens=4_000)
        except Exception as e:
            self._add_gap(f"Executive-summary LLM call failed: {e}")
            return ("_Executive summary could not be generated automatically; see section "
                    "ratings and the top-10 issues below._")

    # -- memo assembly ----------------------------------------------------
    def _ratings_grid_md(self, cards, confidences) -> str:
        rows = ["| Workstream | Rating | Confidence |", "|---|---|---|"]
        emoji = {"Red": "🔴", "Yellow": "🟡", "Green": "🟢"}
        for _no, title, key, *_ in _SECTIONS:
            card = cards.get(key, {})
            rating = card.get("rating", "—") if card.get("present") else "n/a"
            rows.append(f"| {title} | {emoji.get(rating,'')} {rating} | {confidences.get(key,'—')} |")
        return "\n".join(rows)

    def _overall_recommendation(self, cross_row, cards) -> str:
        crit = cross_row.get("critical_issue_count") or 0
        reds = sum(1 for c in cards.values() if c.get("present") and c.get("rating") == "Red")
        return (f"{crit} Critical and {reds} Red-rated workstream(s) identified. "
                "This is an analyst work product — issues are presented for the deal team to "
                "resolve, not as a final recommendation. See the top-10 issues.")

    # -- run() ------------------------------------------------------------
    def run(self, company_name: str, spark, llm_endpoint: str, catalog: str = "uc13",
            manifest: Optional[dict] = None) -> dict:
        self._reset_state()
        self._company_name = company_name
        self._catalog = catalog
        run_id = str(uuid.uuid4())

        from agents.orchestration.pipeline import collect_result_cards
        print("  Collecting result cards (compact) ...")
        cards = collect_result_cards(spark, company_name, catalog)

        cross_row = self._load_row("cross_analysis", company_name, spark)
        if not cross_row:
            self._add_gap("cross_analysis output not found — memo will omit cross-workstream "
                          "reconciliation and top-10 issues. Run the Cross-Analysis Agent.")

        non_banked = self._is_non_banked(company_name, spark)
        confidences = {k: self._section_confidence(cards.get(k), non_banked)
                       for _n, _t, k, *_ in _SECTIONS}

        print("  Running coherence validation (§11.1) ...")
        coherence_log = self._coherence_check(cards, cross_row, confidences, company_name, spark)

        print("  Generating executive summary (single bounded LLM call) ...")
        exec_summary = self._exec_summary(cards, confidences, cross_row, llm_endpoint)

        print("  Assembling section narratives (one bounded call per workstream) ...")
        section_md = {}
        for section in _SECTIONS:
            _no, title, key, *_ = section
            print(f"    · Section {_no}: {title}")
            section_md[key] = self._section_narrative(section, company_name, spark,
                                                      llm_endpoint, cards.get(key))

        # Cross-analysis section (deterministic markdown from its own module).
        cross_md = ""
        if cross_row:
            try:
                from agents.workstreams.cross_analysis_agent import generate_cross_analysis_assessment
                cross_md = generate_cross_analysis_assessment(cross_row, spark=spark,
                                                              catalog=catalog, write_to_volume=False)
            except Exception as e:
                cross_md = f"_Cross-analysis section render error: {e}_"

        # ── Assemble the memo (spec §11.2 memo structure) ──────────────
        ratings_grid = self._ratings_grid_md(cards, confidences)
        overall = self._overall_recommendation(cross_row, cards)
        run_manifest = manifest or {"note": "run manifest not supplied to Orchestrator"}

        memo = [
            f"# Diligence Memo — {company_name}",
            f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · run `{run_id[:8]}`_",
            "",
            "## Executive Summary", "", exec_summary, "",
            f"> **Overall:** {overall}", "",
            "## Section Ratings Grid", "", ratings_grid, "",
        ]
        for _no, title, key, *_ in _SECTIONS:
            memo += [f"## {_no}. {title}  ·  Confidence: {confidences.get(key,'—')}", "",
                     section_md.get(key, ""), ""]
        memo += ["## 8. Cross-Analysis", "", cross_md or "_Not available._", ""]
        memo += [
            "## Appendix A — Agent Run Manifest", "",
            _fmt_manifest_md(run_manifest), "",
            "## Appendix B — Methodology & Provenance", "",
            "Every extracted fact carries a source citation (document, location, confidence). "
            "Section narratives are produced by each workstream agent from its own structured "
            "output; cross-workstream reconciliation and the top-10 issues come from the "
            "Cross-Analysis Agent. This memo is an analyst work product for the deal team to "
            "verify and override.", "",
            "### Coherence validation log", "",
            "| Rule | Workstream | Status | Detail |", "|---|---|---|---|",
        ]
        for c in coherence_log:
            memo.append(f"| {c['rule']} | {c.get('workstream','')} | {c['status']} | {c['detail']} |")
        memo.append("")
        memo_text = "\n".join(memo)

        # ── Write .md and .docx ────────────────────────────────────────
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
        safe = company_name.replace(" ", "_").replace("/", "_")
        d = f"/Volumes/{catalog}/analysis/reports/{safe}"
        os.makedirs(d, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        versioned_stem = f"final_diligence_memo_{safe}_{ts}"
        md_path = f"{d}/{versioned_stem}.md"
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(memo_text)
        print(f"  ✓ Memo markdown → {md_path}")

        docx_path = f"{d}/{versioned_stem}.docx"
        try:
            convert = _load_convert_md_to_word()
            convert(md_path, docx_path)
            print(f"  ✓ Memo Word → {docx_path}")
        except Exception as e:
            self._add_gap(f"Word export failed: {e}")
            docx_path = None

        section_ratings = {k: cards.get(k, {}).get("rating") for _n, _t, k, *_ in _SECTIONS}

        return {
            "company_name":              company_name,
            "run_id":                    run_id,
            "overall_recommendation":    overall,
            "executive_summary":         exec_summary,
            "section_ratings_json":      json.dumps(section_ratings),
            "section_confidence_json":   json.dumps(confidences),
            "top_10_issues_json":        cross_row.get("top_10_issues_json") or "[]",
            "reconciliation_summary_json": cross_row.get("reconciliation_summary_json") or "{}",
            "data_room_gap_list_json":   cross_row.get("data_room_gap_list_json") or "[]",
            "coherence_log_json":        json.dumps(coherence_log),
            "agent_run_manifest_json":   json.dumps(run_manifest),
            "citations_json":            cross_row.get("citations") or "[]",
            "deliverables_json":         json.dumps({"memo_md": md_path, "memo_docx": docx_path}),
            "report_md_path":            md_path,
            "report_docx_path":          docx_path,
            "created_at":                datetime.now(timezone.utc).isoformat(),
            "memo_markdown":             memo_text,   # convenience for notebook rendering
        }


# ---------------------------------------------------------------------------
# Table DDL (extensible — deliverables_json hook for future PPT/PDF/dashboard)
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name                 STRING,
    run_id                       STRING,
    overall_recommendation       STRING,
    executive_summary            STRING,
    section_ratings_json         STRING,
    section_confidence_json      STRING,
    top_10_issues_json           STRING,
    reconciliation_summary_json  STRING,
    data_room_gap_list_json      STRING,
    coherence_log_json           STRING,
    agent_run_manifest_json      STRING,
    citations_json               STRING,
    deliverables_json            STRING,
    report_md_path               STRING,
    report_docx_path             STRING,
    created_at                   TIMESTAMP
) USING DELTA
"""


def main(manifest: Optional[dict] = None) -> dict:
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    company_name = get_param("sp_company_name")
    catalog      = get_param("catalog",      default="uc13")
    llm_endpoint = get_param("llm_endpoint", default="databricks-claude-sonnet-4-6")

    from pyspark.sql import SparkSession
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Orchestrator Agent ({company_name}) ===")
    agent  = OrchestratorAgent()
    result = agent.run(company_name=company_name, spark=spark,
                       llm_endpoint=llm_endpoint, catalog=catalog, manifest=manifest)

    table = f"{catalog}.analysis.diligence_report"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

    _EXPECTED_COLS = {
        "company_name", "run_id", "overall_recommendation", "executive_summary",
        "section_ratings_json", "section_confidence_json", "top_10_issues_json",
        "reconciliation_summary_json", "data_room_gap_list_json", "coherence_log_json",
        "agent_run_manifest_json", "citations_json", "deliverables_json",
        "report_md_path", "report_docx_path", "created_at",
    }
    try:
        _live = {f.name for f in spark.table(table).schema.fields}
        if not _EXPECTED_COLS.issubset(_live):
            print(f"  [schema_migration] {table}: dropping stale table. Missing: "
                  f"{sorted(_EXPECTED_COLS - _live)}")
            spark.sql(f"DROP TABLE IF EXISTS {table}")
    except Exception:
        pass

    spark.sql(_CREATE_TABLE_SQL.format(table=table))
    # No DELETE — every run appends a new row. Use run_id + created_at to identify versions.

    from pyspark.sql import Row
    from pyspark.sql.types import StructType, StructField, StringType, TimestampType
    schema = StructType([StructField(c, StringType(), True) for c in (
        "company_name", "run_id", "overall_recommendation", "executive_summary",
        "section_ratings_json", "section_confidence_json", "top_10_issues_json",
        "reconciliation_summary_json", "data_room_gap_list_json", "coherence_log_json",
        "agent_run_manifest_json", "citations_json", "deliverables_json",
        "report_md_path", "report_docx_path")]
        + [StructField("created_at", TimestampType(), True)])

    row_data = {c: result.get(c) for c in (
        "company_name", "run_id", "overall_recommendation", "executive_summary",
        "section_ratings_json", "section_confidence_json", "top_10_issues_json",
        "reconciliation_summary_json", "data_room_gap_list_json", "coherence_log_json",
        "agent_run_manifest_json", "citations_json", "deliverables_json",
        "report_md_path", "report_docx_path")}
    row_data["created_at"] = datetime.now(timezone.utc)

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(table)
    print(f"\n✓ Saved diligence report metadata → {table}")
    print(f"✓ Memo: {result.get('report_md_path')}")
    print(f"✓ Word: {result.get('report_docx_path')}")
    return result


if __name__ == "__main__":
    main()
