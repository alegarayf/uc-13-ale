"""Onboarding cluster helper — serverless submit for M4 runbook Steps 3 and 5.

Uploads eval/retrieval (and databricks/agents for harness PYTHONPATH), submits
serverless jobs with pyyaml + pydantic>=2.0 + mlflow, polls to completion.

Usage (from repo root):
  python eval/program/onboarding_cluster_submit.py bootstrap --company "Clearsulting"
  python eval/program/onboarding_cluster_submit.py harness-baseline --company "Clearsulting"
  python eval/program/onboarding_cluster_submit.py sync

Loads repo-root `.env`; never prints tokens.
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")

from databricks.sdk import WorkspaceClient  # noqa: E402
from databricks.sdk.service.compute import Environment  # noqa: E402
from databricks.sdk.service.jobs import JobEnvironment, SparkPythonTask, SubmitTask  # noqa: E402
from databricks.sdk.service.workspace import ImportFormat  # noqa: E402

DEFAULT_CATALOG = "uc13_ale"
ONBOARDING_DEPS = ["pyyaml", "pydantic>=2.0", "mlflow"]
SYNC_DIRS = ("eval/retrieval", "databricks/agents")
SKIP_SUFFIXES = {".pyc", ".pyo"}
BASELINE_RUN_ID_RE = re.compile(r"^baseline_[0-9a-f]+$", re.MULTILINE)

BOOTSTRAP_DRIVER = '''\
"""Onboarding Step 3 — gold bootstrap (serverless driver)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path("{repo_root}")
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))
os.environ["PYTHONPATH"] = str(REPO_ROOT)

from eval.retrieval.gold import bootstrap

rc = bootstrap.main(["--company", "{company}", "--catalog", "{catalog}"])
if rc != 0:
    sys.exit(rc)
'''

HARNESS_DRIVER = '''\
"""Onboarding Step 5 — harness baseline (serverless driver)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path("{repo_root}")
DATABRICKS_ROOT = REPO_ROOT / "databricks"
os.chdir(REPO_ROOT)
for path in (str(DATABRICKS_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ["PYTHONPATH"] = f"{DATABRICKS_ROOT}:{REPO_ROOT}"

from eval.retrieval import harness_cli

rc = harness_cli.main(
    [
        "run",
        "--store-backend",
        "delta",
        "--run-type",
        "baseline",
        "--company-name",
        "{company}",
        "--catalog",
        "{catalog}",
    ]
)
if rc != 0:
    sys.exit(rc)
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


def sync_onboarding_code(w: WorkspaceClient | None = None) -> int:
    """Upload eval/retrieval and databricks/agents trees to the workspace."""
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
            if fp.suffix in SKIP_SUFFIXES or "__pycache__" in fp.parts:
                continue
            ws_path = f"{root}/{fp.relative_to(REPO).as_posix()}"
            import_file(w, ws_path, fp)
            uploaded += 1
    print(f"synced {uploaded} files -> {root}")
    return uploaded


def _upload_driver(w: WorkspaceClient, user: str, name: str, source: str) -> str:
    driver_path = f"/Users/{user}/{name}"
    import_bytes(w, driver_path, source.encode())
    print(f"uploaded driver -> {driver_path}")
    return driver_path


def submit_serverless(
    w: WorkspaceClient,
    *,
    python_file: str,
    run_name: str,
    timeout_seconds: int = 7200,
) -> tuple[int, str, int | None]:
    run = w.jobs.submit(
        run_name=run_name,
        timeout_seconds=timeout_seconds,
        environments=[
            JobEnvironment(
                environment_key="default",
                spec=Environment(client="1", dependencies=ONBOARDING_DEPS),
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
    while True:
        st = w.jobs.get_run(run_id)
        life = st.state.life_cycle_state.value if st.state and st.state.life_cycle_state else None
        result = st.state.result_state.value if st.state and st.state.result_state else None
        print(f"  status life={life} result={result}")
        if life in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            break
        time.sleep(30)

    task_run_id = st.tasks[0].run_id if st.tasks else run_id
    out = w.jobs.get_run_output(task_run_id)
    logs = (out.logs or "") + (out.error or "")
    if out.error:
        print("ERROR:", out.error)
    if logs:
        print("--- logs tail ---")
        print(logs[-12000:] if len(logs) > 12000 else logs)
    return run_id, logs, 0 if result == "SUCCESS" else 1


def _slug(company: str) -> str:
    return company.replace(" ", "_").lower()


def run_bootstrap(company: str, catalog: str = DEFAULT_CATALOG, *, sync: bool = True) -> int:
    """Runbook Step 3: eval.retrieval.gold.bootstrap on serverless."""
    w = client()
    user = workspace_user(w)
    repo_root = ws_repo_root(user)
    if sync:
        sync_onboarding_code(w)
    driver = _upload_driver(
        w,
        user,
        "onboarding_bootstrap_runner.py",
        BOOTSTRAP_DRIVER.format(company=company, catalog=catalog, repo_root=repo_root),
    )
    run_id, _logs, rc = submit_serverless(
        w,
        python_file=driver,
        run_name=f"onboarding-bootstrap-{_slug(company)}",
    )
    print(f"DATABRICKS_RUN_ID={run_id}")
    return rc


def run_harness_baseline(company: str, catalog: str = DEFAULT_CATALOG, *, sync: bool = True) -> int:
    """Runbook Step 5: eval.retrieval.harness_cli baseline on serverless."""
    w = client()
    user = workspace_user(w)
    repo_root = ws_repo_root(user)
    if sync:
        sync_onboarding_code(w)
    driver = _upload_driver(
        w,
        user,
        "onboarding_harness_runner.py",
        HARNESS_DRIVER.format(company=company, catalog=catalog, repo_root=repo_root),
    )
    run_id, logs, rc = submit_serverless(
        w,
        python_file=driver,
        run_name=f"onboarding-harness-baseline-{_slug(company)}",
    )
    print(f"DATABRICKS_RUN_ID={run_id}")
    if rc != 0 and BASELINE_RUN_ID_RE.search(logs):
        # T9 quirk: harness_cli success via SystemExit(0) can surface as INTERNAL_ERROR.
        print("note: baseline run_id found in logs; treating as success")
        return 0
    return rc


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Onboarding serverless cluster submit (Steps 3 & 5)")
    sub = ap.add_subparsers(dest="command", required=True)

    sync_p = sub.add_parser("sync", help="Upload eval/retrieval + databricks/agents only")
    sync_p.set_defaults(func=lambda _a: sync_onboarding_code() or 0)

    for name, fn, help_text in (
        ("bootstrap", run_bootstrap, "Runbook Step 3 — gold bootstrap"),
        ("harness-baseline", run_harness_baseline, "Runbook Step 5 — harness baseline"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--company", required=True, help='SharePoint display name (e.g. "Clearsulting")')
        p.add_argument("--catalog", default=DEFAULT_CATALOG, help=f"Unity Catalog (default: {DEFAULT_CATALOG})")
        p.add_argument("--no-sync", action="store_true", help="Skip workspace upload (use stale workspace copy)")
        p.set_defaults(
            func=lambda a, _fn=fn: _fn(a.company, a.catalog, sync=not a.no_sync),
        )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
