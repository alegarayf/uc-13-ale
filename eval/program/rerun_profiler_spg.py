"""Re-run Company Profiler for SPG on serverless (eval-signal-foldback M7 T1).

Laptop entry: syncs code to the workspace, uploads a cluster driver, submits a
serverless SparkPythonTask, and polls to a terminal state. Does not invoke
``company_profiler.main()`` locally (no local Spark).

Cluster driver: sets ``sp_company_name`` / ``catalog`` / ``schema`` on
``os.environ`` (``get_param()`` does not read ``sys.argv``), then calls
``company_profiler.main()`` without modifying that module.

Usage (from repo root):
  python eval/program/rerun_profiler_spg.py
"""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")

from databricks.sdk import WorkspaceClient  # noqa: E402
from databricks.sdk.service.compute import Environment  # noqa: E402
from databricks.sdk.service.jobs import JobEnvironment, SparkPythonTask, SubmitTask  # noqa: E402
from databricks.sdk.service.workspace import ImportFormat  # noqa: E402

COMPANY_NAME = "SPG"
CATALOG = "uc13_ale"
SCHEMA = "classification"
RUN_NAME = "m7-t1-profiler-spg"
TIMEOUT_SECONDS = 3600
POLL_SECONDS = 20
JOB_DEPS = ["pyyaml", "pydantic>=2.0", "mlflow"]
SYNC_DIRS = ("eval/retrieval", "databricks/agents", "databricks/jobs")
SKIP_SUFFIXES = {".pyc", ".pyo", ".ipynb", ".sqlite"}

CLUSTER_DRIVER = '''\
"""SPG Company Profiler re-run — cluster driver (M7 T1)."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path("__REPO_ROOT__")
DATABRICKS_ROOT = REPO_ROOT / "databricks"
os.chdir(str(DATABRICKS_ROOT))
for path in (str(DATABRICKS_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ["PYTHONPATH"] = str(DATABRICKS_ROOT) + ":" + str(REPO_ROOT)
os.environ["sp_company_name"] = "__COMPANY_NAME__"
os.environ["catalog"] = "__CATALOG__"
os.environ["schema"] = "__SCHEMA__"

print(
    "profiler_rerun company=%s catalog=%s schema=%s cwd=%s"
    % (
        os.environ["sp_company_name"],
        os.environ["catalog"],
        os.environ["schema"],
        os.getcwd(),
    )
)

profiler_path = DATABRICKS_ROOT / "jobs" / "scripts" / "company_profiler.py"
spec = importlib.util.spec_from_file_location("company_profiler", profiler_path)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load company_profiler from %s" % profiler_path)
mod = importlib.util.module_from_spec(spec)
sys.modules["company_profiler"] = mod
spec.loader.exec_module(mod)
mod.main()
'''


def client() -> WorkspaceClient:
    return WorkspaceClient(
        host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        token=os.environ["DATABRICKS_TOKEN"],
    )


def workspace_user(w: WorkspaceClient | None = None) -> str:
    w = w or client()
    return w.current_user.me().user_name


def ws_repo_root(user: str | None = None) -> str:
    user = user or workspace_user()
    return f"/Workspace/Users/{user}/uc-13-ale"


def import_bytes(w: WorkspaceClient, workspace_path: str, content: bytes) -> None:
    w.workspace.import_(
        path=workspace_path,
        format=ImportFormat.AUTO,
        content=base64.b64encode(content).decode(),
        overwrite=True,
    )


def import_file(w: WorkspaceClient, workspace_path: str, local_path: Path) -> None:
    import_bytes(w, workspace_path, local_path.read_bytes())


def sync_profiler_code(w: WorkspaceClient | None = None) -> int:
    """Upload eval/retrieval, databricks/agents, and databricks/jobs (no notebooks)."""
    w = w or client()
    user = workspace_user(w)
    root = ws_repo_root(user)
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
            import_file(w, ws_path, fp)
            uploaded += 1
    print(f"synced {uploaded} files -> {root}")
    return uploaded


def _render_driver(repo_root: str) -> str:
    return (
        CLUSTER_DRIVER.replace("__REPO_ROOT__", repo_root)
        .replace("__COMPANY_NAME__", COMPANY_NAME)
        .replace("__CATALOG__", CATALOG)
        .replace("__SCHEMA__", SCHEMA)
    )


def _upload_driver(w: WorkspaceClient, user: str, source: str) -> str:
    driver_path = f"/Users/{user}/rerun_profiler_spg_driver.py"
    import_bytes(w, driver_path, source.encode())
    print(f"uploaded driver -> {driver_path}")
    return driver_path


def submit_and_poll(
    w: WorkspaceClient,
    *,
    python_file: str,
    run_name: str,
    timeout_seconds: int = TIMEOUT_SECONDS,
) -> tuple[int, str | None, str | None, int]:
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
        print("--- logs tail ---")
        tail = logs[-12000:] if len(logs) > 12000 else logs
        try:
            print(tail)
        except UnicodeEncodeError:
            print(tail.encode("ascii", "replace").decode("ascii"))
    rc = 0 if result == "SUCCESS" else 1
    return run_id, life, result, rc


def main() -> int:
    w = client()
    user = workspace_user(w)
    repo_root = ws_repo_root(user)
    print(
        f"company={COMPANY_NAME} catalog={CATALOG} schema={SCHEMA} "
        f"repo_root={repo_root}"
    )
    if COMPANY_NAME != "SPG":
        raise RuntimeError(
            "sp_company_name / COMPANY_NAME must be the literal 'SPG' "
            "(Coupling Surface 11: lowercase 'spg' silently matches zero warehouse rows)"
        )
    sync_profiler_code(w)
    driver = _upload_driver(w, user, _render_driver(repo_root))
    run_id, life, result, rc = submit_and_poll(
        w,
        python_file=driver,
        run_name=RUN_NAME,
    )
    print(f"DATABRICKS_RUN_ID={run_id}")
    print(f"TERMINAL life={life} result={result} rc={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
