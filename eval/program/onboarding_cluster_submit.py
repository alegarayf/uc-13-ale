"""Onboarding cluster helper — serverless submit for M4 runbook Steps 3 and 5.

Uploads eval/retrieval (and databricks/agents for harness PYTHONPATH), submits
serverless jobs with pyyaml + pydantic>=2.0 + mlflow, polls to completion.

Usage (from repo root):
  python eval/program/onboarding_cluster_submit.py bootstrap --company "Clearsulting"
  python eval/program/onboarding_cluster_submit.py export-gold --company "Clearsulting"
  python eval/program/onboarding_cluster_submit.py harness-baseline --company "Clearsulting" --no-sync
  python eval/program/onboarding_cluster_submit.py sync

If the workspace gold changed (e.g. after `bootstrap`), run `export-gold` to pull
it back to the laptop with encoding-safe raw-byte writes (never a text-mode
write, so no OS-locale codepage can silently re-encode UTF-8 into a corrupt
single byte), then run `harness-baseline --no-sync` so the harness job's own
code-sync step doesn't re-upload a stale local gold copy over the fresh
workspace-bootstrapped one.

Loads repo-root `.env`; never prints tokens.
"""
from __future__ import annotations

import argparse
import base64
import json
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
from databricks.sdk.service.workspace import ExportFormat, ImportFormat  # noqa: E402

DEFAULT_CATALOG = "uc13_ale"
ONBOARDING_DEPS = ["pyyaml", "pydantic>=2.0", "mlflow"]
SYNC_DIRS = ("eval/retrieval", "databricks/agents")
SKIP_SUFFIXES = {".pyc", ".pyo"}
BASELINE_RUN_ID_RE = re.compile(r"^baseline_[0-9a-f]+$", re.MULTILINE)
HARNESS_CLI_RUN_ID_RE = re.compile(r"harness_cli: run_id=(\S+)")
GATE_PASS_LOG_RE = re.compile(r"gate_pass=(True|False|None)", re.IGNORECASE)

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
os.environ["PYTHONPATH"] = f"{{DATABRICKS_ROOT}}:{{REPO_ROOT}}"

from eval.retrieval import harness_cli

argv = [
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
{gold_path_argv}
rc = harness_cli.main(argv)
if rc != 0:
    sys.exit(rc)
'''

HARNESS_ENHANCEMENT_DRIVER = '''\
"""Onboarding M1 — harness enhancement/ablation (serverless driver)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path("{repo_root}")
DATABRICKS_ROOT = REPO_ROOT / "databricks"
os.chdir(REPO_ROOT)
for path in (str(DATABRICKS_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ["PYTHONPATH"] = f"{{DATABRICKS_ROOT}}:{{REPO_ROOT}}"

from eval.retrieval import harness_cli

argv = [
    "run",
    "--store-backend",
    "delta",
    "--run-type",
    "{run_type}",
    "--company-name",
    "{company}",
    "--catalog",
    "{catalog}",
    "--baseline-ref-run-id",
    "{baseline_ref_run_id}",
]
{affected_intents_argv}
{ablation_config_argv}
{gold_path_argv}
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    rc = harness_cli.main(argv)
_captured = _buf.getvalue()
print(_captured, end="")
if rc != 0:
    sys.exit(rc)
_match = re.search(r"harness_cli: run_id=(\\S+)", _captured)
if _match:
    _run_id = _match.group(1)
    _report_path = REPO_ROOT / "eval" / "retrieval" / "reports" / f"{{_run_id}}.json"
    if _report_path.is_file():
        _gate_pass = json.loads(_report_path.read_text(encoding="utf-8")).get("manifest", {{}}).get("gate_pass")
        print(f"gate_pass={{_gate_pass}}")
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


def export_gold(
    company: str,
    catalog: str = DEFAULT_CATALOG,  # noqa: ARG001 - kept for CLI symmetry with bootstrap/harness-baseline
    *,
    local_path: Path | None = None,
) -> int:
    """Pull the workspace-generated gold YAML for `company` back to the laptop.

    Downloads raw bytes via ``workspace.export`` (base64-decoded) and writes them
    with ``Path.write_bytes`` — never through a text-mode ``open()``/``write_text()``
    layer — so no OS-locale codepage (e.g. cp1252 on Windows) can ever silently
    re-encode UTF-8 multi-byte characters (such as U+2014 em dash) into a single
    invalid byte (0x97). See .dev/wave1.5-remediation-2026-08-19/0x97-byte-investigation.md.

    Validates the downloaded bytes decode as UTF-8 before writing; refuses to write
    (and returns non-zero) if the workspace copy itself is not valid UTF-8.
    """
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from eval.retrieval.companies import canonical_company_slug
    from eval.retrieval.harness import default_gold_path

    slug = canonical_company_slug(company)
    dest = local_path or default_gold_path(slug)

    w = client()
    user = workspace_user(w)
    repo_root = ws_repo_root(user)
    ws_path = f"{repo_root}/eval/retrieval/gold_labels/{slug}.yaml"

    export_resp = w.workspace.export(ws_path, format=ExportFormat.AUTO)
    if not export_resp.content:
        print(f"export-gold: empty export response for {ws_path}", file=sys.stderr)
        return 1
    decoded_bytes = base64.b64decode(export_resp.content)

    try:
        decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(
            f"export-gold: workspace copy at {ws_path} is NOT valid UTF-8 "
            f"({exc}); refusing to write corrupt bytes to {dest}",
            file=sys.stderr,
        )
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(decoded_bytes)

    # Re-read what we just wrote (belt-and-suspenders against any write-path
    # surprise) and re-validate before declaring success.
    written = dest.read_bytes()
    try:
        written.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(
            f"export-gold: post-write validation FAILED for {dest} ({exc}); "
            "local file may be corrupt",
            file=sys.stderr,
        )
        return 1

    print(
        f"export-gold: wrote {len(written)} bytes -> {dest} "
        f"(source: {ws_path}, valid_utf8=True)"
    )
    return 0


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
        f"onboarding_bootstrap_runner_{_slug(company)}.py",
        BOOTSTRAP_DRIVER.format(company=company, catalog=catalog, repo_root=repo_root),
    )
    run_id, _logs, rc = submit_serverless(
        w,
        python_file=driver,
        run_name=f"onboarding-bootstrap-{_slug(company)}",
    )
    print(f"DATABRICKS_RUN_ID={run_id}")
    return rc


def run_harness_baseline(
    company: str,
    catalog: str = DEFAULT_CATALOG,
    *,
    gold_path: str | None = None,
    sync: bool = True,
) -> int:
    """Runbook Step 5: eval.retrieval.harness_cli baseline on serverless."""
    w = client()
    user = workspace_user(w)
    repo_root = ws_repo_root(user)
    if sync:
        sync_onboarding_code(w)
    gold_path_argv = ""
    if gold_path:
        gold_path_argv = f'argv.extend(["--gold-path", "{gold_path}"])'
    driver = _upload_driver(
        w,
        user,
        f"onboarding_harness_runner_{_slug(company)}.py",
        HARNESS_DRIVER.format(
            company=company,
            catalog=catalog,
            repo_root=repo_root,
            gold_path_argv=gold_path_argv,
        ),
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


def run_harness_enhancement(
    company: str,
    catalog: str = DEFAULT_CATALOG,
    *,
    run_type: str,
    baseline_ref_run_id: str,
    affected_intents: list[str] | None = None,
    ablation_config: dict | None = None,
    gold_path: str | None = None,
    sync: bool = True,
) -> int:
    """M1 — eval.retrieval.harness_cli enhancement or ablation on serverless."""
    if run_type not in {"enhancement", "ablation"}:
        raise ValueError(f"unsupported run_type: {run_type!r}")
    if run_type == "enhancement" and not affected_intents:
        raise ValueError("run_type enhancement requires --affected-intents")
    if run_type == "ablation" and affected_intents:
        raise ValueError("run_type ablation must not include --affected-intents")

    print(f"company={company} run_type={run_type} catalog={catalog}")

    w = client()
    user = workspace_user(w)
    repo_root = ws_repo_root(user)
    if sync:
        sync_onboarding_code(w)

    affected_intents_argv = ""
    if affected_intents:
        affected_intents_argv = f"argv.extend({['--affected-intents', *affected_intents]!r})"

    ablation_config_argv = ""
    if ablation_config is not None:
        ablation_config_argv = (
            f'argv.extend(["--ablation-config", {json.dumps(json.dumps(ablation_config))}])'
        )

    gold_path_argv = ""
    if gold_path:
        gold_path_argv = f'argv.extend(["--gold-path", "{gold_path}"])'

    driver = _upload_driver(
        w,
        user,
        f"onboarding_harness_{run_type}_{_slug(company)}.py",
        HARNESS_ENHANCEMENT_DRIVER.format(
            company=company,
            catalog=catalog,
            repo_root=repo_root,
            run_type=run_type,
            baseline_ref_run_id=baseline_ref_run_id,
            affected_intents_argv=affected_intents_argv,
            ablation_config_argv=ablation_config_argv,
            gold_path_argv=gold_path_argv,
        ),
    )
    run_id, logs, rc = submit_serverless(
        w,
        python_file=driver,
        run_name=f"onboarding-harness-{run_type}-{_slug(company)}",
    )
    print(f"DATABRICKS_RUN_ID={run_id}")

    harness_match = HARNESS_CLI_RUN_ID_RE.search(logs)
    if harness_match:
        print(f"HARNESS_RUN_ID={harness_match.group(1)}")

    gate_pass_match = GATE_PASS_LOG_RE.search(logs)
    if gate_pass_match:
        print(f"gate_pass={gate_pass_match.group(1)}")

    if rc != 0 and HARNESS_CLI_RUN_ID_RE.search(logs):
        print("note: harness_cli run_id found in logs; treating as success")
        return 0
    return rc


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Onboarding serverless cluster submit (Steps 3 & 5)")
    sub = ap.add_subparsers(dest="command", required=True)

    sync_p = sub.add_parser("sync", help="Upload eval/retrieval + databricks/agents only")
    sync_p.set_defaults(func=lambda _a: sync_onboarding_code() or 0)

    export_p = sub.add_parser(
        "export-gold",
        help=(
            "Download the workspace-bootstrapped gold YAML back to the laptop "
            "(encoding-safe: raw bytes, UTF-8 validated). Run this after "
            "`bootstrap` and before `harness-baseline --no-sync` whenever the "
            "workspace gold changed, to avoid a stale local copy being "
            "re-uploaded and to avoid any text-mode re-encoding corruption."
        ),
    )
    export_p.add_argument("--company", required=True, help='SharePoint display name (e.g. "Clearsulting")')
    export_p.add_argument("--catalog", default=DEFAULT_CATALOG, help=f"Unity Catalog (default: {DEFAULT_CATALOG})")
    export_p.add_argument(
        "--local-path",
        type=Path,
        default=None,
        help="Override local destination (default: eval/retrieval/gold_labels/<canonical_slug>.yaml)",
    )
    export_p.set_defaults(
        func=lambda a: export_gold(a.company, a.catalog, local_path=a.local_path)
    )

    for name, fn, help_text in (
        ("bootstrap", run_bootstrap, "Runbook Step 3 — gold bootstrap"),
        ("harness-baseline", run_harness_baseline, "Runbook Step 5 — harness baseline"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--company", required=True, help='SharePoint display name (e.g. "Clearsulting")')
        p.add_argument("--catalog", default=DEFAULT_CATALOG, help=f"Unity Catalog (default: {DEFAULT_CATALOG})")
        p.add_argument("--no-sync", action="store_true", help="Skip workspace upload (use stale workspace copy)")
        if name == "harness-baseline":
            p.add_argument(
                "--gold-path",
                help="Explicit gold YAML path (required for non-Elder Care baselines)",
            )
        p.set_defaults(
            func=(
                (lambda a, _fn=fn: _fn(
                    a.company,
                    a.catalog,
                    gold_path=getattr(a, "gold_path", None),
                    sync=not a.no_sync,
                ))
                if name == "harness-baseline"
                else (lambda a, _fn=fn: _fn(a.company, a.catalog, sync=not a.no_sync))
            ),
        )

    harness_run_p = sub.add_parser(
        "harness-run",
        help="M1 — harness enhancement or ablation run",
    )
    harness_run_p.add_argument(
        "--company",
        required=True,
        help='SharePoint display name (e.g. "Clearsulting")',
    )
    harness_run_p.add_argument(
        "--run-type",
        required=True,
        choices=("enhancement", "ablation"),
        help="Harness run type (enhancement requires --affected-intents; ablation must omit it)",
    )
    harness_run_p.add_argument(
        "--baseline-ref-run-id",
        required=True,
        help="Pinned baseline run_id to compare against",
    )
    harness_run_p.add_argument(
        "--affected-intents",
        help="Comma-separated intent ids (required for enhancement; omit for ablation)",
    )
    harness_run_p.add_argument(
        "--ablation-config",
        help='Ablation arm JSON, e.g. \'{"arm": "merge_rank_off"}\'',
    )
    harness_run_p.add_argument(
        "--catalog",
        default=DEFAULT_CATALOG,
        help=f"Unity Catalog (default: {DEFAULT_CATALOG})",
    )
    harness_run_p.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip workspace upload (use stale workspace copy)",
    )
    harness_run_p.add_argument(
        "--gold-path",
        help="Explicit gold YAML path (required for non-Elder Care runs)",
    )
    harness_run_p.set_defaults(
        func=lambda a: run_harness_enhancement(
            a.company,
            a.catalog,
            run_type=a.run_type,
            baseline_ref_run_id=a.baseline_ref_run_id,
            affected_intents=(
                [part.strip() for part in a.affected_intents.split(",") if part.strip()]
                if a.affected_intents
                else None
            ),
            ablation_config=json.loads(a.ablation_config) if a.ablation_config else None,
            gold_path=a.gold_path,
            sync=not a.no_sync,
        )
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
