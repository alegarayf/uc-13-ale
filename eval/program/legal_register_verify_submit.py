"""Serverless submit wrapper for ``verify_legal_register`` (eval-signal-foldback M8 T2).

Laptop-side sync + submit + poll, mirroring ``onboarding_cluster_submit.py``.
Does not call ``verify_legal_register`` locally — G4 verifier writes are
serverless-job only.

Usage (from repo root)::

    python eval/program/legal_register_verify_submit.py sync
    python eval/program/legal_register_verify_submit.py verify --company "Clearsulting" --catalog uc13_ale
    python eval/program/legal_register_verify_submit.py verify --company "GKF" --catalog uc13_ale --no-sync

Loads repo-root ``.env``; never prints tokens.
"""
from __future__ import annotations

import argparse
import base64
import os
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = "uc13_ale"
ONBOARDING_DEPS = ["pyyaml", "pydantic>=2.0", "mlflow"]
SYNC_DIRS = ("eval/content", "eval/retrieval", "eval/program")
SKIP_SUFFIXES = {".pyc", ".pyo"}
TIMEOUT_SECONDS = 7200
POLL_SECONDS = 30
DRIVER_RELPATH = Path("eval/program/_legal_register_verify_driver.py")

LAUNCHER = '''\
"""Legal-register verify — serverless launcher (M8 T2)."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path("{repo_root}")
os.chdir(str(REPO_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ["PYTHONPATH"] = str(REPO_ROOT)

# T9 (amendment): make_sdk_sql_executor()'s load_dotenv() is a no-op on this
# cluster (no .env file is uploaded here). Set the three vars it reads before
# the driver import below, so the warehouse client can be built on-cluster.
os.environ["DATABRICKS_SERVER_HOSTNAME"] = {databricks_server_hostname!r}
os.environ["DATABRICKS_TOKEN"] = {databricks_token!r}
os.environ["DATABRICKS_HTTP_PATH"] = {databricks_http_path!r}

driver_path = REPO_ROOT / "eval" / "program" / "_legal_register_verify_driver.py"
spec = importlib.util.spec_from_file_location("legal_register_verify_driver", driver_path)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load %s" % driver_path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
mod.main({company}, {run_id}, {catalog})
'''


def mint_run_id(ts: datetime | None = None) -> str:
    """Mint an S2 ``run_id`` via the existing ``spot_check._generate_run_id`` scheme."""
    from eval.content.spot_check import _generate_run_id

    run_id, _run_ts = _generate_run_id(ts)
    return run_id


def client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(
        host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        token=os.environ["DATABRICKS_TOKEN"],
    )


def workspace_user(w=None) -> str:
    w = w or client()
    return w.current_user.me().user_name


def ws_repo_root(user: str | None = None) -> str:
    user = user or workspace_user()
    return f"/Workspace/Users/{user}/uc-13-ale"


def import_bytes(w, workspace_path: str, content: bytes) -> None:
    from databricks.sdk.service.workspace import ImportFormat

    w.workspace.import_(
        path=workspace_path,
        format=ImportFormat.AUTO,
        content=base64.b64encode(content).decode(),
        overwrite=True,
    )


def import_file(w, workspace_path: str, local_path: Path) -> None:
    import_bytes(w, workspace_path, local_path.read_bytes())


def sync_verify_code(w=None) -> int:
    """Upload eval/content, eval/retrieval, and eval/program to the workspace."""
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


def _slug(company: str) -> str:
    from eval.retrieval.companies import canonical_company_slug

    return canonical_company_slug(company)


def _render_launcher(
    repo_root: str,
    company: str,
    run_id: str,
    catalog: str,
    *,
    server_hostname: str,
    token: str,
    http_path: str,
) -> str:
    return LAUNCHER.format(
        repo_root=repo_root,
        company=repr(company),
        run_id=repr(run_id),
        catalog=repr(catalog),
        databricks_server_hostname=server_hostname,
        databricks_token=token,
        databricks_http_path=http_path,
    )


def _upload_driver(w, user: str, source: str) -> str:
    driver_path = f"/Users/{user}/legal_register_verify_driver_{int(time.time())}.py"
    import_bytes(w, driver_path, source.encode())
    print(f"uploaded driver -> {driver_path}")
    return driver_path


def submit_serverless(
    w,
    *,
    python_file: str,
    run_name: str,
    timeout_seconds: int = TIMEOUT_SECONDS,
) -> tuple[int, str, int | None]:
    from databricks.sdk.service.compute import Environment
    from databricks.sdk.service.jobs import JobEnvironment, SparkPythonTask, SubmitTask

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
        time.sleep(POLL_SECONDS)

    task_run_id = st.tasks[0].run_id if st.tasks else run_id
    out = w.jobs.get_run_output(task_run_id)
    logs = (out.logs or "") + (out.error or "")
    if out.error:
        print("ERROR:", out.error)
    if logs:
        print("--- logs tail ---")
        print(logs[-12000:] if len(logs) > 12000 else logs)
    return run_id, logs, 0 if result == "SUCCESS" else 1


def _upload_wrapper_and_driver(w, repo_root: str) -> None:
    import_file(w, f"{repo_root}/{DRIVER_RELPATH.as_posix()}", REPO / DRIVER_RELPATH)
    import_file(
        w,
        f"{repo_root}/eval/program/legal_register_verify_submit.py",
        Path(__file__).resolve(),
    )


def run_verify(company: str, catalog: str = DEFAULT_CATALOG, *, sync: bool = True) -> int:
    """Submit ``verify_legal_register`` as a serverless SparkPythonTask."""
    # T9 (amendment): read these before any workspace call so a missing var
    # fails fast on the laptop, not on-cluster (A6).
    server_hostname = os.environ["DATABRICKS_SERVER_HOSTNAME"]
    token = os.environ["DATABRICKS_TOKEN"]
    http_path = os.environ["DATABRICKS_HTTP_PATH"]
    run_id = mint_run_id()
    w = client()
    user = workspace_user(w)
    repo_root = ws_repo_root(user)
    if sync:
        sync_verify_code(w)
    else:
        _upload_wrapper_and_driver(w, repo_root)
        print(f"uploaded wrapper+driver -> {repo_root} (--no-sync)")
    launcher = _upload_driver(
        w,
        user,
        _render_launcher(
            repo_root,
            company,
            run_id,
            catalog,
            server_hostname=server_hostname,
            token=token,
            http_path=http_path,
        ),
    )
    databricks_run_id, _logs, rc = submit_serverless(
        w,
        python_file=launcher,
        run_name=f"legal-register-verify-{_slug(company)}",
    )
    print(f"S2_RUN_ID={run_id}")
    print(f"DATABRICKS_RUN_ID={databricks_run_id}")
    return rc


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Serverless submit for verify_legal_register (G4)"
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sync_p = sub.add_parser("sync", help="Upload eval/content + eval/retrieval + eval/program")
    sync_p.set_defaults(func=lambda _a: sync_verify_code() or 0)

    verify_p = sub.add_parser("verify", help="Submit verify_legal_register on serverless")
    verify_p.add_argument(
        "--company",
        required=True,
        help='SharePoint display name (e.g. "Clearsulting")',
    )
    verify_p.add_argument(
        "--catalog",
        default=DEFAULT_CATALOG,
        help=f"Unity Catalog (default: {DEFAULT_CATALOG})",
    )
    verify_p.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip workspace tree upload (still uploads wrapper + driver)",
    )
    verify_p.set_defaults(
        func=lambda a: run_verify(a.company, a.catalog, sync=not a.no_sync)
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
