"""
pipeline.py — UC13 diligence pipeline orchestrator (execution layer).

This is the SINGLE SOURCE OF TRUTH for the Phase 3 → Phase 5 dependency graph.
A thin Databricks job (one task) calls ``run_pipeline(company_name)``; the same
function runs verbatim in ``test_pipeline.ipynb``. There is deliberately NO
duplicate DAG in the Workflow YAML — dependency, retry, and failure-isolation
logic all live here so they cannot drift out of sync.

Design principles (see the plan discussion):

1. Delta tables are the data bus. Every agent persists a row to
   ``uc13.analysis.*``; downstream agents read those rows. The orchestrator never
   passes large objects between agents in memory.

2. ``to_result_card()`` is the ONLY interchange format the Cross-Analysis and
   Orchestrator agents consume for reasoning. It is size-bounded by construction,
   so context never blows up regardless of how verbose an upstream agent is. It
   reads the compact ``*_json`` summary columns — never chunks, embeddings, or
   ``reasoning_trace``.

3. Failure isolation. Each agent runs with retries. If it still fails, agents
   that HARD-depend on it are SKIPPED; agents that only SOFT-depend on it run in
   degraded mode (their graceful ``_load_*`` fallbacks already handle a missing
   upstream table). Independent agents always continue. The run manifest records
   SUCCESS / FAILED / SKIPPED + attempts + error per agent and is persisted into
   the final report.

4. Parallelism. Independent agents run concurrently via a wave scheduler backed by
   a ThreadPoolExecutor. Each agent's MLflow ``@mlflow.trace`` spans are emitted
   per-thread (thread-local trace context), so per-agent tracing is preserved.
"""

from __future__ import annotations

import importlib
import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Agent registry — the DAG
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentSpec:
    key: str                     # short name / manifest key
    module: str                  # importable module path exposing main()
    table: str                   # uc13.analysis.<table> written by the agent
    phase: str                   # "3" workstream · "4" cross-analysis · "5" orchestrator
    hard_deps: tuple = ()        # must SUCCEED, else this agent is SKIPPED
    soft_deps: tuple = ()        # waited on, but agent runs degraded if they fail


# Phase 3 workstream agents (spec §3), Phase 4 Cross-Analysis (§4), Phase 5 Orchestrator (§5).
# Ordering encodes the dependencies discovered in the agent source (not just the
# working-session diagram): Legal ← CQA (contract_trigger_list); QofE ← FTA (+CQA);
# Forecast ← FTA (+QofE, +CQA). See each agent's _load_* methods.
AGENT_REGISTRY: dict[str, AgentSpec] = {
    "business_model": AgentSpec(
        "business_model", "agents.workstreams.business_model_agent",
        "business_model", phase="3"),
    "financial_trends": AgentSpec(
        "financial_trends", "agents.workstreams.financial_trends_agent",
        "financial_trends", phase="3"),
    "customer_quality": AgentSpec(
        "customer_quality", "agents.workstreams.customer_quality_agent",
        "customer_quality", phase="3"),
    "kpi": AgentSpec(
        "kpi", "agents.workstreams.kpi_agent",
        "kpi", phase="3"),
    "legal_contracts": AgentSpec(
        "legal_contracts", "agents.workstreams.legal_contracts_agent",
        "legal_contracts", phase="3", soft_deps=("customer_quality",)),
    "quality_of_earnings": AgentSpec(
        "quality_of_earnings", "agents.workstreams.quality_of_earnings_agent",
        "quality_of_earnings", phase="3",
        hard_deps=("financial_trends",), soft_deps=("customer_quality",)),
    "forecast": AgentSpec(
        "forecast", "agents.workstreams.forecast_agent",
        "forecast", phase="3",
        hard_deps=("financial_trends",), soft_deps=("quality_of_earnings", "customer_quality")),
    "cross_analysis": AgentSpec(
        "cross_analysis", "agents.workstreams.cross_analysis_agent",
        "cross_analysis", phase="4",
        # Cross-Analysis reconciles across all workstreams. None is individually
        # hard — it degrades each check to "cannot_check" when an input is missing —
        # but it must WAIT for all Phase 3 agents to reach a terminal state.
        soft_deps=("business_model", "financial_trends", "customer_quality", "kpi",
                   "legal_contracts", "quality_of_earnings", "forecast")),
    "orchestrator": AgentSpec(
        "orchestrator", "agents.orchestration.orchestrator_agent",
        "diligence_report", phase="5",
        hard_deps=("cross_analysis",),
        soft_deps=("business_model", "financial_trends", "customer_quality", "kpi",
                   "legal_contracts", "quality_of_earnings", "forecast")),
}

_TERMINAL = {"SUCCESS", "FAILED", "SKIPPED"}


# ---------------------------------------------------------------------------
# Result cards — the bounded interchange format
# ---------------------------------------------------------------------------

def _derive_rating(flags: list) -> str:
    """Overall traffic-light rating from a flag list (worst severity wins)."""
    sev = {str(f.get("severity", "")).lower() for f in (flags or [])}
    if "red" in sev:
        return "Red"
    if "yellow" in sev:
        return "Yellow"
    return "Green"


def _load_flags(row: dict) -> list:
    raw = row.get("flags")
    if not raw:
        return []
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []


# Per-agent extractors: pull the few high-signal metrics into the card.
# Each returns a small dict. Kept deliberately tiny to cap context.
def _metrics_business_model(row):
    return {
        "revenue_model": row.get("revenue_model_tag"),
        "revenue_durability_flag": row.get("revenue_durability_flag"),
        "overlay_conflict": row.get("overlay_conflict"),
    }

def _metrics_financial_trends(row):
    def _first(colname):
        try:
            arr = json.loads(row.get(colname) or "[]")
            return arr[:3]
        except Exception:
            return []
    return {
        "addback_pct_of_ebitda": row.get("addback_pct_of_ebitda"),
        "revenue_trend": _first("revenue_trend_json"),
        "ebitda": _first("ebitda_json"),
    }

def _metrics_customer_quality(row):
    try:
        conc = json.loads(row.get("concentration_summary_json") or "{}")
    except Exception:
        conc = {}
    try:
        ret = json.loads(row.get("retention_json") or "{}")
    except Exception:
        ret = {}
    return {"concentration_summary": conc, "retention": ret}

def _metrics_kpi(row):
    try:
        missing = json.loads(row.get("missing_kpis_json") or "[]")
    except Exception:
        missing = []
    return {"overlay_confirmed": row.get("overlay_confirmed"),
            "missing_kpi_count": len(missing)}

def _metrics_legal(row):
    def _len(colname):
        try:
            return len(json.loads(row.get(colname) or "[]"))
        except Exception:
            return 0
    return {"coc_consent_items": _len("coc_consent_list_json"),
            "open_litigation_items": _len("litigation_register_json"),
            "contracts_reviewed": _len("contract_register_json")}

def _metrics_qofe(row):
    try:
        scen = json.loads(row.get("ebitda_scenarios_json") or "{}")
    except Exception:
        scen = {}
    return {"total_addbacks_pct_of_ebitda": row.get("total_addbacks_pct_of_ebitda"),
            "tier4_addback_count": row.get("tier4_addback_count"),
            "ebitda_scenarios": scen}

def _metrics_forecast(row):
    try:
        counts = json.loads(row.get("credibility_summary_json") or "{}")
    except Exception:
        counts = {}
    return {"credibility_summary": counts,
            "stretch_assumption_count": row.get("stretch_assumption_count"),
            "forecast_source_present": row.get("forecast_source_present")}

_METRIC_EXTRACTORS: dict[str, Callable] = {
    "business_model": _metrics_business_model,
    "financial_trends": _metrics_financial_trends,
    "customer_quality": _metrics_customer_quality,
    "kpi": _metrics_kpi,
    "legal_contracts": _metrics_legal,
    "quality_of_earnings": _metrics_qofe,
    "forecast": _metrics_forecast,
}

# Cap on flags carried in a card — Cross-Analysis re-reads full flags from Delta
# only for the specific checks that need them.
_MAX_CARD_FLAGS = 12


def to_result_card(spark, agent_key: str, company_name: str, catalog: str = "uc13") -> Optional[dict]:
    """Return a size-bounded summary card for one workstream agent, or None.

    Reads the agent's most-recent Delta row and normalizes it to:
        { workstream, rating, headline, key_metrics{..}, flags[..],
          data_room_gaps[..], citations_ref, present, created_at }

    Never reads chunks/embeddings/reasoning_trace. Returns None (with no error)
    when the agent has not run — callers treat that as "not available".
    """
    spec = AGENT_REGISTRY.get(agent_key)
    table = f"{catalog}.analysis.{spec.table if spec else agent_key}"
    try:
        rows = spark.sql(
            f"SELECT * FROM {table} WHERE company_name = :c "
            "ORDER BY created_at DESC LIMIT 1",
            args={"c": company_name},
        ).collect()
    except Exception:
        return None
    if not rows:
        return None

    row = rows[0].asDict()
    flags = _load_flags(row)
    extractor = _METRIC_EXTRACTORS.get(agent_key)
    key_metrics = extractor(row) if extractor else {}

    gaps = row.get("data_room_gaps") or []
    if isinstance(gaps, str):
        try:
            gaps = json.loads(gaps)
        except Exception:
            gaps = [gaps]

    return {
        "workstream": agent_key,
        "present": True,
        "rating": _derive_rating(flags),
        "headline": (row.get("executive_summary") or "")[:600],
        "key_metrics": key_metrics,
        "flags": flags[:_MAX_CARD_FLAGS],
        "flag_count": len(flags),
        "data_room_gaps": gaps,
        "citations_ref": f"{table} (column: citations)",
        "created_at": str(row.get("created_at")),
    }


def collect_result_cards(spark, company_name: str, catalog: str = "uc13",
                         agent_keys: Optional[list] = None) -> dict:
    """Collect result cards for the given (default: all Phase 3) agents.

    Missing agents map to {"workstream": key, "present": False}. Total payload is
    a handful of KB — safe to feed into an LLM prompt directly.
    """
    keys = agent_keys or [k for k, s in AGENT_REGISTRY.items() if s.phase == "3"]
    cards = {}
    for k in keys:
        card = to_result_card(spark, k, company_name, catalog)
        cards[k] = card if card else {"workstream": k, "present": False}
    return cards


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------

@dataclass
class AgentRun:
    key: str
    status: str = "PENDING"          # PENDING | RUNNING | SUCCESS | FAILED | SKIPPED
    attempts: int = 0
    error: Optional[str] = None
    degraded_from: list = field(default_factory=list)  # soft deps that failed
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_s: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "agent": self.key, "status": self.status, "attempts": self.attempts,
            "error": self.error, "degraded_from": self.degraded_from,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "duration_s": self.duration_s,
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    """Runs the Phase 3→5 DAG with parallelism, retry, and failure isolation."""

    def __init__(self, company_name: str, catalog: str = "uc13",
                 llm_endpoint: str = "databricks-claude-sonnet-4-6",
                 extraction_endpoint: Optional[str] = None,
                 max_retries: int = 2, retry_backoff_s: float = 10.0,
                 max_parallelism: int = 4,
                 registry: Optional[dict] = None):
        self.company_name = company_name
        self.catalog = catalog
        self.llm_endpoint = llm_endpoint
        self.extraction_endpoint = extraction_endpoint or llm_endpoint
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s
        self.max_parallelism = max_parallelism
        self.registry = registry or AGENT_REGISTRY
        self.runs: dict[str, AgentRun] = {k: AgentRun(k) for k in self.registry}
        # Capture the calling thread's SparkSession so _invoke can pass it to
        # agent main() functions. ThreadPoolExecutor workers have an empty
        # thread-local getActiveSession(); passing it explicitly avoids all
        # Databricks-specific thread-local quirks.
        from pyspark.sql import SparkSession as _SS
        self._spark = _SS.getActiveSession()

    # -- environment ----------------------------------------------------
    def _sync_env(self):
        """Mirror params into os.environ so agent main()s (which use get_param →
        widgets/env) read consistent values in worker threads."""
        os.environ["sp_company_name"] = self.company_name
        os.environ["catalog"] = self.catalog
        os.environ["llm_endpoint"] = self.llm_endpoint
        os.environ["extraction_endpoint"] = self.extraction_endpoint
        os.environ["RE2_CATALOG"] = self.catalog
        os.environ["RE2_STORE_BACKEND"] = "delta"

    # -- scheduling -----------------------------------------------------
    def _ready(self, key: str) -> Optional[str]:
        """Return 'run', 'skip', or None (not-ready) for a PENDING agent.

        - Skip if any HARD dep is not SUCCESS (i.e. FAILED/SKIPPED).
        - Not-ready until every hard+soft dep has reached a terminal state.
        - Otherwise run (degraded if any soft dep is non-SUCCESS).
        """
        spec = self.registry[key]
        for d in spec.hard_deps:
            st = self.runs[d].status
            if st in ("FAILED", "SKIPPED"):
                return "skip"
        all_deps = tuple(spec.hard_deps) + tuple(spec.soft_deps)
        for d in all_deps:
            if self.runs[d].status not in _TERMINAL:
                return None
        return "run"

    def _degraded_soft_deps(self, key: str) -> list:
        spec = self.registry[key]
        return [d for d in spec.soft_deps if self.runs[d].status != "SUCCESS"]

    # -- single agent execution ----------------------------------------
    def _run_agent(self, key: str) -> AgentRun:
        run = self.runs[key]
        spec = self.registry[key]
        run.degraded_from = self._degraded_soft_deps(key)
        run.status = "RUNNING"
        run.started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.time()

        self._sync_env()
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            run.attempts = attempt
            try:
                self._invoke(spec, key)
                run.status = "SUCCESS"
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001 — isolation is the whole point
                last_err = f"{type(exc).__name__}: {exc}"
                tb = traceback.format_exc(limit=4)
                print(f"  [{key}] attempt {attempt}/{self.max_retries} FAILED: {last_err}\n{tb}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_s)
        if last_err is not None:
            run.status = "FAILED"
            run.error = last_err

        run.finished_at = datetime.now(timezone.utc).isoformat()
        run.duration_s = round(time.time() - t0, 1)
        deg = f" (degraded: missing {run.degraded_from})" if run.degraded_from else ""
        print(f"  [{key}] → {run.status} in {run.duration_s}s (attempts={run.attempts}){deg}")
        return run

    def _invoke(self, spec: AgentSpec, key: str):
        """Import the agent module and call its main(). Isolated per-agent MLflow
        trace context — each agent's @mlflow.trace spans attach to its own thread.

        Passes spark=self._spark so agents running in ThreadPoolExecutor worker
        threads don't have to rely on SparkSession.getActiveSession() (which is
        thread-local and empty in workers). Agents that don't accept a spark
        keyword argument (legacy or external) are called without it via fallback.
        """
        module = importlib.import_module(spec.module)
        if not hasattr(module, "main"):
            raise RuntimeError(f"module {spec.module} has no main()")
        import inspect
        _accepts_spark = "spark" in inspect.signature(module.main).parameters
        _kwargs = {"spark": self._spark} if _accepts_spark and self._spark is not None else {}
        try:
            import mlflow
            with mlflow.start_span(name=f"agent::{key}"):
                module.main(**_kwargs)
        except ImportError:
            module.main(**_kwargs)

    # -- orchestration loop --------------------------------------------
    def run(self, only_phases: tuple = ("3", "4", "5")) -> dict:
        """Execute the DAG. Returns the run manifest dict."""
        self._sync_env()
        print(f"\n=== PipelineOrchestrator: {self.company_name} "
              f"(phases {','.join(only_phases)}, max_parallelism={self.max_parallelism}) ===")

        # Mark out-of-scope phases as SKIPPED up front so scheduling ignores them.
        active = {k for k, s in self.registry.items() if s.phase in only_phases}
        for k, s in self.registry.items():
            if k not in active:
                self.runs[k].status = "SKIPPED"
                self.runs[k].error = f"phase {s.phase} not in scope"

        with ThreadPoolExecutor(max_workers=self.max_parallelism) as pool:
            while any(self.runs[k].status == "PENDING" for k in active):
                # Resolve skips first (agents whose hard dep failed).
                progressed = False
                wave = []
                for k in active:
                    if self.runs[k].status != "PENDING":
                        continue
                    decision = self._ready(k)
                    if decision == "skip":
                        self.runs[k].status = "SKIPPED"
                        failed_hard = [d for d in self.registry[k].hard_deps
                                       if self.runs[d].status in ("FAILED", "SKIPPED")]
                        self.runs[k].error = f"skipped — hard dependency not satisfied: {failed_hard}"
                        print(f"  [{k}] → SKIPPED (hard dep {failed_hard})")
                        progressed = True
                    elif decision == "run":
                        wave.append(k)

                if wave:
                    for k in wave:
                        self.runs[k].status = "RUNNING"
                    futures = {pool.submit(self._run_agent, k): k for k in wave}
                    for _ in as_completed(futures):
                        pass
                    progressed = True

                if not progressed:
                    # Deadlock guard — should not happen with a valid DAG.
                    stuck = [k for k in active if self.runs[k].status == "PENDING"]
                    for k in stuck:
                        self.runs[k].status = "SKIPPED"
                        self.runs[k].error = "unresolved dependency (possible cycle)"
                    print(f"  [orchestrator] deadlock guard tripped for {stuck}")
                    break

        return self.manifest()

    def manifest(self) -> dict:
        runs = [self.runs[k].to_dict() for k in self.registry]
        summary = {st: sum(1 for r in runs if r["status"] == st)
                   for st in ("SUCCESS", "FAILED", "SKIPPED")}
        return {
            "company_name": self.company_name,
            "catalog": self.catalog,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "runs": runs,
        }


# ---------------------------------------------------------------------------
# Convenience entry point (called by the Databricks job and the test notebook)
# ---------------------------------------------------------------------------

def run_pipeline(company_name: Optional[str] = None,
                 catalog: str = "uc13",
                 llm_endpoint: str = "databricks-claude-sonnet-4-6",
                 extraction_endpoint: Optional[str] = None,
                 run_orchestrator: bool = True,
                 max_parallelism: int = 4,
                 max_retries: int = 2) -> dict:
    """Run the diligence DAG for one company and return the run manifest.

    Phases 3 (workstreams) + 4 (Cross-Analysis) run through the parallel DAG.
    Phase 5 (Orchestrator) then runs explicitly so it can receive the run manifest
    (the generic DAG invoker cannot pass it). Set run_orchestrator=False to stop
    after Phase 4 (e.g. to inspect agent outputs before generating the memo).

    company_name falls back to the sp_company_name widget/env var (job param).
    """
    if company_name is None:
        # Lazy import to avoid a hard dependency when called with an explicit name.
        from agents.workstreams.forecast_agent import get_param
        company_name = get_param("sp_company_name")

    orch = PipelineOrchestrator(
        company_name=company_name, catalog=catalog,
        llm_endpoint=llm_endpoint, extraction_endpoint=extraction_endpoint,
        max_retries=max_retries, max_parallelism=max_parallelism,
    )
    # DAG covers Phase 3 + 4. Phase 5 is driven below so the memo embeds the manifest.
    manifest = orch.run(only_phases=("3", "4"))

    orch_result = None
    if run_orchestrator:
        cross_ok = orch.runs["cross_analysis"].status == "SUCCESS"
        run = orch.runs["orchestrator"]
        if not cross_ok:
            run.status = "SKIPPED"
            run.error = "skipped — cross_analysis did not succeed"
            print("  [orchestrator] → SKIPPED (cross_analysis not successful)")
        else:
            import time as _time
            run.status = "RUNNING"
            run.started_at = datetime.now(timezone.utc).isoformat()
            _t0 = _time.time()
            try:
                from agents.orchestration import orchestrator_agent
                orch._sync_env()
                try:
                    import mlflow
                    with mlflow.start_span(name="agent::orchestrator"):
                        orch_result = orchestrator_agent.main(manifest=manifest)
                except ImportError:
                    orch_result = orchestrator_agent.main(manifest=manifest)
                run.status = "SUCCESS"
                run.attempts = 1
            except Exception as exc:  # noqa: BLE001
                run.status = "FAILED"
                run.attempts = 1
                run.error = f"{type(exc).__name__}: {exc}"
                print(f"  [orchestrator] → FAILED: {run.error}")
            run.finished_at = datetime.now(timezone.utc).isoformat()
            run.duration_s = round(_time.time() - _t0, 1)
        # Refresh manifest to reflect the orchestrator run.
        manifest = orch.manifest()
        if isinstance(orch_result, dict):
            manifest["report_md_path"] = orch_result.get("report_md_path")
            manifest["report_docx_path"] = orch_result.get("report_docx_path")

    print("\n=== Run manifest ===")
    print(json.dumps(manifest["summary"], indent=2))
    for r in manifest["runs"]:
        if r["status"] in ("FAILED", "SKIPPED"):
            print(f"  {r['agent']}: {r['status']} — {r['error']}")
    return manifest


if __name__ == "__main__":
    run_pipeline()
