"""Pipeline run attribution — pipeline_thread_id + per-agent agent_run_id (M-RE2 T1)."""

from __future__ import annotations

import logging
import os
import subprocess
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from eval.retrieval.models import HarnessRun
from eval.retrieval.store import DeltaEvalStore, EvalStore, SqliteEvalStore

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_PIPELINE_THREAD_ID: ContextVar[str | None] = ContextVar(
    "pipeline_thread_id",
    default=None,
)
_AGENT_RUN_ID: ContextVar[str | None] = ContextVar("agent_run_id", default=None)
_CURRENT_AGENT_ID: ContextVar[str | None] = ContextVar("current_agent_id", default=None)
_ACTIVE_STORE: ContextVar[EvalStore | None] = ContextVar("active_store", default=None)

_PIPELINE_RUN_SENTINEL = "pipeline-run"


class RunContextError(RuntimeError):
    """Invalid run_context lifecycle (double open, close without open)."""


def set_pipeline_thread(thread_id: str) -> None:
    """Bind the outer pipeline envelope id for all subsequent agent runs."""
    _PIPELINE_THREAD_ID.set(thread_id)


def get_pipeline_thread() -> str | None:
    return _PIPELINE_THREAD_ID.get()


def get_agent_run_id() -> str | None:
    return _AGENT_RUN_ID.get()


def get_current_agent_id() -> str | None:
    return _CURRENT_AGENT_ID.get()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_sqlite_path() -> Path:
    return _repo_root() / "eval" / "retrieval" / ".local" / "re2_store.sqlite"


def _git_sha() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=_repo_root(),
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def _resolve_store(store: EvalStore | None) -> EvalStore:
    if store is not None:
        return store
    return SqliteEvalStore(_default_sqlite_path())


def _store_backend_label(store: EvalStore) -> str:
    if isinstance(store, DeltaEvalStore):
        return "delta"
    return "sqlite"


def _pipeline_pin(field: str) -> str:
    return os.environ.get(field, _PIPELINE_RUN_SENTINEL)


def open_agent_run(
    agent_id: str,
    *,
    company_name: str,
    catalog: str,
    affected_intents: list[str],
    store: EvalStore | None = None,
) -> str:
    """Open a per-agent pipeline manifest (incomplete) before provenance writes."""
    if _AGENT_RUN_ID.get() is not None:
        raise RunContextError(
            f"agent run already open for {_CURRENT_AGENT_ID.get()!r}; "
            "call close_agent_run() first"
        )

    resolved_store = _resolve_store(store)
    pipeline_thread_id = get_pipeline_thread()
    agent_run_id = uuid.uuid4().hex

    manifest = HarnessRun(
        run_id=agent_run_id,
        run_type="pipeline",
        pipeline_thread_id=pipeline_thread_id,
        company_name=company_name,
        catalog=catalog,
        ingestion_snapshot=_pipeline_pin("RE2_INGESTION_SNAPSHOT"),
        registry_hash=_pipeline_pin("RE2_REGISTRY_HASH"),
        gold_snapshot=_pipeline_pin("RE2_GOLD_SNAPSHOT"),
        git_sha=_git_sha(),
        affected_intents=list(affected_intents),
        gated_intents=[],
        store_backend=_store_backend_label(resolved_store),
        harness_status="incomplete",
        intent_count=len(affected_intents),
        created_at=datetime.now(timezone.utc),
    )
    resolved_store.insert_run(manifest)

    _CURRENT_AGENT_ID.set(agent_id)
    _AGENT_RUN_ID.set(agent_run_id)
    _ACTIVE_STORE.set(resolved_store)

    logger.info(
        "open_agent_run agent_id=%s agent_run_id=%s pipeline_thread_id=%s intent_count=%s",
        agent_id,
        agent_run_id,
        pipeline_thread_id,
        len(affected_intents),
    )
    return agent_run_id


def close_agent_run() -> HarnessRun:
    """Finalize the open agent run with provenance-derived fallback/empty rates."""
    agent_run_id = _AGENT_RUN_ID.get()
    if agent_run_id is None:
        raise RunContextError("close_agent_run called with no open agent run")

    store = _ACTIVE_STORE.get()
    if store is None:
        raise RunContextError("close_agent_run called with no active store")

    fallback_rate, empty_rate = store.compute_provenance_rates(agent_run_id)
    finalized = store.finalize_run(
        agent_run_id,
        gate_pass=None,
        fallback_rate=fallback_rate,
        empty_rate=empty_rate,
    )

    logger.info(
        "close_agent_run agent_id=%s agent_run_id=%s fallback_rate=%s empty_rate=%s",
        _CURRENT_AGENT_ID.get(),
        agent_run_id,
        fallback_rate,
        empty_rate,
    )

    _CURRENT_AGENT_ID.set(None)
    _AGENT_RUN_ID.set(None)
    _ACTIVE_STORE.set(None)
    return finalized
