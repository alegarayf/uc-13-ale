"""Promote SPG W2c golden-checklist scores (eval-signal-foldback M7 T6).

Laptop entry: syncs ``eval/retrieval`` plus this file to the workspace, uploads a
cluster driver, and submits a serverless SparkPythonTask. Does not call
``evaluate_promotion`` / ``record_e2e_linkage`` locally (no local Spark).

Cluster driver: constructs ``DeltaEvalStore(spark, catalog="uc13_ale")`` and
calls frozen ``evaluate_promotion`` for the five gate agents, then frozen
``record_e2e_linkage`` for Legal (agent-id ``legal``, never ``lca``) and FTA
(agent-id ``fta``). FTA's checklist-level weighted score is 8.5/18; this
script writes the operator-pinned integer stand-in ``8`` (floor of 8.5)
because ``e2e_checklist_score`` is a frozen INT column.

Usage (from repo root)::

    python eval/program/promote_w2c_spg.py
"""
from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

RUN_ID = "445878b36e06407385b9498dcab265c7"
COMPANY_NAME = "SPG"
CATALOG = "uc13_ale"
EXPECTED_PROMOTION_STATUS = "baseline_bootstrap"
LEGAL_AGENT_ID = "legal"
LEGAL_CHECKLIST_SCORE = 1
LEGAL_CHECKLIST_TOTAL = 11
LEGAL_SNAPSHOT_TABLE = "uc13_ale.analysis.legal"
FTA_AGENT_ID = "fta"
FTA_SNAPSHOT_TABLE = "uc13_ale.analysis.financial_trends"
# T2–T5 checklists remain the score-of-record (read-only). Hub column is INT; floor, not round.
FTA_CHECKLIST_SCORE = 8
FTA_CHECKLIST_TOTAL = 18
RUN_NAME = "m7-t6-promote-w2c-spg"
TIMEOUT_SECONDS = 3600
POLL_SECONDS = 20
JOB_DEPS = ["pyyaml", "pydantic>=2.0", "mlflow"]
SYNC_DIRS = ("eval/retrieval",)
SKIP_SUFFIXES = {".pyc", ".pyo", ".ipynb", ".sqlite"}

# Scores copied from each checklist's Summary line at T6 execution
# (T2 ee30dca / T3 1a24603 / T4 93f05ab / T5 0258807). Do not invent replacements.
# FTA is not in this tuple — direct record_e2e_linkage with literal 8/18.
# Tuple rows: (e2e_agent_id, candidate_score, candidate_total, e2e_snapshot_table).
# Plain tuples (not dataclass) so importlib-loaded cluster import works on Py3.10.
GATE_CALLS: tuple[tuple[str, int, int, str], ...] = (
    ("bma", 7, 7, "uc13_ale.analysis.business_model"),
    ("cqa", 3, 6, "uc13_ale.analysis.customer_quality"),
    ("kpi", 1, 3, "uc13_ale.analysis.kpi"),
    ("qoe", 3, 5, "uc13_ale.analysis.quality_of_earnings"),
    ("profiler", 5, 7, "uc13_ale.classification.company_profile"),
)

CLUSTER_DRIVER = '''\
"""SPG W2c promotion — cluster driver (M7 T6)."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path("__REPO_ROOT__")
os.chdir(str(REPO_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ["PYTHONPATH"] = str(REPO_ROOT)

from pyspark.sql import SparkSession

spark = SparkSession.getActiveSession()
if spark is None:
    raise RuntimeError("Active SparkSession required for delta backend")

mod_path = REPO_ROOT / "eval" / "program" / "promote_w2c_spg.py"
spec = importlib.util.spec_from_file_location("promote_w2c_spg", mod_path)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load %s" % mod_path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
mod.run_promotion(spark)
'''


def run_promotion(spark: Any) -> None:
    """Cluster path: five gate-agent promotions, then Legal and FTA linkage."""
    from eval.retrieval.promotion_gate import evaluate_promotion
    from eval.retrieval.scripts.record_e2e_linkage import record_e2e_linkage
    from eval.retrieval.store import DeltaEvalStore

    if COMPANY_NAME != "SPG":
        raise SystemExit(
            f"HALT: company_name must be 'SPG', got {COMPANY_NAME!r}"
        )
    if LEGAL_AGENT_ID != "legal":
        raise SystemExit(
            f"HALT: Legal e2e_agent_id must be 'legal', got {LEGAL_AGENT_ID!r}"
        )
    if FTA_AGENT_ID != "fta":
        raise SystemExit(
            f"HALT: FTA e2e_agent_id must be 'fta', got {FTA_AGENT_ID!r}"
        )
    if CATALOG != "uc13_ale":
        raise SystemExit(f"HALT: catalog must be 'uc13_ale', got {CATALOG!r}")
    if FTA_CHECKLIST_SCORE != 8 or FTA_CHECKLIST_TOTAL != 18:
        raise SystemExit(
            f"HALT: FTA integer stand-in must be 8/18, got "
            f"{FTA_CHECKLIST_SCORE}/{FTA_CHECKLIST_TOTAL}"
        )

    store = DeltaEvalStore(spark, catalog=CATALOG)

    for e2e_agent_id, candidate_score, candidate_total, e2e_snapshot_table in GATE_CALLS:
        result = evaluate_promotion(
            store,
            RUN_ID,
            e2e_agent_id=e2e_agent_id,
            company_name=COMPANY_NAME,
            catalog=CATALOG,
            candidate_score=candidate_score,
            candidate_total=candidate_total,
            e2e_snapshot_table=e2e_snapshot_table,
        )
        print(repr(result))
        if result.status != EXPECTED_PROMOTION_STATUS:
            raise SystemExit(
                f"HALT: evaluate_promotion({e2e_agent_id!r}) expected "
                f"status={EXPECTED_PROMOTION_STATUS!r}, got {result!r}"
            )

    legal_manifest = record_e2e_linkage(
        RUN_ID,
        e2e_agent_id="legal",
        e2e_checklist_score=LEGAL_CHECKLIST_SCORE,
        e2e_checklist_total=LEGAL_CHECKLIST_TOTAL,
        e2e_snapshot_table=LEGAL_SNAPSHOT_TABLE,
        store=store,
    )
    print(repr(legal_manifest))

    # Floor of T-series weighted 8.5/18. Literal int 8 — not 8.5, 9, or 14.
    fta_manifest = record_e2e_linkage(
        RUN_ID,
        e2e_agent_id="fta",
        e2e_checklist_score=8,
        e2e_checklist_total=18,
        e2e_snapshot_table=FTA_SNAPSHOT_TABLE,
        store=store,
    )
    print(repr(fta_manifest))
    if fta_manifest.e2e_checklist_score != 8:
        raise SystemExit(
            f"HALT: FTA linkage score must be 8, got {fta_manifest.e2e_checklist_score!r}"
        )


def _client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(
        host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        token=os.environ["DATABRICKS_TOKEN"],
    )


def _workspace_user(w) -> str:
    return w.current_user.me().user_name


def _ws_repo_root(user: str) -> str:
    return f"/Workspace/Users/{user}/uc-13-ale"


def _import_bytes(w, workspace_path: str, content: bytes) -> None:
    from databricks.sdk.service.workspace import ImportFormat

    w.workspace.import_(
        path=workspace_path,
        format=ImportFormat.AUTO,
        content=base64.b64encode(content).decode(),
        overwrite=True,
    )


def _import_file(w, workspace_path: str, local_path: Path) -> None:
    _import_bytes(w, workspace_path, local_path.read_bytes())


def _sync_eval_retrieval(w) -> int:
    user = _workspace_user(w)
    root = _ws_repo_root(user)
    w.workspace.mkdirs(root)
    uploaded = 0
    for rel in SYNC_DIRS:
        local_root = REPO / rel
        if not local_root.exists():
            print(f"SKIP missing {rel}")
            continue
        for fp in local_root.rglob("*"):
            if not fp.is_file():
                continue
            if fp.suffix in SKIP_SUFFIXES or "__pycache__" in fp.parts or ".local" in fp.parts:
                continue
            ws_path = f"{root}/{fp.relative_to(REPO).as_posix()}"
            _import_file(w, ws_path, fp)
            uploaded += 1
    script_ws = f"{root}/eval/program/promote_w2c_spg.py"
    _import_file(w, script_ws, Path(__file__).resolve())
    uploaded += 1
    print(f"synced {uploaded} files -> {root}")
    return uploaded


def _render_driver(repo_root: str) -> str:
    return CLUSTER_DRIVER.replace("__REPO_ROOT__", repo_root)


def _upload_driver(w, user: str, source: str) -> str:
    driver_path = f"/Users/{user}/promote_w2c_spg_driver.py"
    _import_bytes(w, driver_path, source.encode())
    print(f"uploaded driver -> {driver_path}")
    return driver_path


def _submit_and_poll(
    w,
    *,
    python_file: str,
    run_name: str,
    timeout_seconds: int = TIMEOUT_SECONDS,
) -> tuple[int, str | None, str | None, int]:
    from databricks.sdk.service.compute import Environment
    from databricks.sdk.service.jobs import JobEnvironment, SparkPythonTask, SubmitTask

    run = w.jobs.submit(
        run_name=run_name,
        timeout_seconds=timeout_seconds,
        environments=[
            JobEnvironment(
                environment_key="default",
                spec=Environment(client="1", dependencies=JOB_DEPS),
            )
        ],
        tasks=[
            SubmitTask(
                task_key="main",
                environment_key="default",
                spark_python_task=SparkPythonTask(python_file=python_file),
                timeout_seconds=timeout_seconds,
            )
        ],
    )
    run_id = run.run_id
    print(f"submitted run_id={run_id} name={run_name}")
    result = None
    life = None
    while True:
        st = w.jobs.get_run(run_id)
        life = st.state.life_cycle_state.value if st.state and st.state.life_cycle_state else None
        result = st.state.result_state.value if st.state and st.state.result_state else None
        print(f"  status life={life} result={result}")
        if life in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            break
        time.sleep(POLL_SECONDS)

    task_run_id = st.tasks[0].run_id if st.tasks else run_id
    out = w.jobs.get_run_output(task_run_id)
    logs = (out.logs or "") + (out.error or "")
    if out.error:
        print("ERROR:", out.error)
    if logs:
        print("--- logs ---")
        try:
            print(logs)
        except UnicodeEncodeError:
            print(logs.encode("ascii", "replace").decode("ascii"))
    rc = 0 if result == "SUCCESS" else 1
    return run_id, life, result, rc


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    w = _client()
    user = _workspace_user(w)
    repo_root = _ws_repo_root(user)
    print(
        f"company={COMPANY_NAME} catalog={CATALOG} pipeline_run_id={RUN_ID} "
        f"repo_root={repo_root}"
    )
    if "--no-sync" in sys.argv:
        script_ws = f"{repo_root}/eval/program/promote_w2c_spg.py"
        _import_file(w, script_ws, Path(__file__).resolve())
        print(f"uploaded script -> {script_ws} (--no-sync)")
    else:
        _sync_eval_retrieval(w)
    driver = _upload_driver(w, user, _render_driver(repo_root))
    databricks_run_id, life, result, rc = _submit_and_poll(
        w,
        python_file=driver,
        run_name=RUN_NAME,
    )
    print(f"DATABRICKS_RUN_ID={databricks_run_id}")
    print(f"TERMINAL life={life} result={result} rc={rc}")
    return rc


if __name__ == "__main__":
    try:
        from pyspark.sql import SparkSession

        _spark = SparkSession.getActiveSession()
    except ImportError:
        _spark = None
    if _spark is not None:
        run_promotion(_spark)
    else:
        raise SystemExit(main())
