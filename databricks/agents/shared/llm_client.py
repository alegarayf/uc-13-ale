"""Unified LLM gateway: one entry point for every chat/vision call to Claude.

Every call site keeps passing the Databricks-style endpoint alias it already
uses today (e.g. "databricks-claude-sonnet-4-6") -- this module translates it
to an Anthropic model ID internally and, on a transient failure, falls back to
the Databricks serving endpoint of the same name. See
`.specs/features/anthropic-sdk-migration/design.md` for the full architecture.

Embeddings never go through this module -- Anthropic has no embeddings API.
`retrieval.py`, `ingestion_parser.get_embeddings_batch`, `doc_worker.py`, and
`ensure_coverage.py` keep calling `mlflow.deployments` directly (AD-001).
"""

from __future__ import annotations

import os

# Explicit table, never a string transform (e.g. `alias.replace("databricks-",
# "")`) -- an unmapped alias must fail loudly with ValueError instead of
# silently producing a model ID the API then rejects far from the call site.
# See databricks/CLAUDE.md "Endpoint names (Databricks model serving)".
_MODEL_MAP: dict[str, str] = {
    "databricks-claude-sonnet-4-6": "claude-sonnet-4-6",
    "databricks-claude-haiku-4-5": "claude-haiku-4-5",
}

_VALID_BACKENDS = frozenset({"anthropic", "databricks"})
_BACKEND_ENV_VAR = "LLM_BACKEND"
_DEFAULT_BACKEND = "anthropic"


def resolve_model(endpoint: str) -> str:
    """Translate a Databricks-style endpoint alias to an Anthropic model ID.

    Raises ValueError naming the unknown alias rather than guessing one.
    """
    try:
        return _MODEL_MAP[endpoint]
    except KeyError:
        raise ValueError(
            f"Unknown LLM endpoint alias {endpoint!r}. Known aliases: "
            f"{sorted(_MODEL_MAP)}. Add it to llm_client._MODEL_MAP first."
        ) from None


def _active_backend() -> str:
    """Read LLM_BACKEND from the environment, defaulting to 'anthropic'.

    Raises ValueError naming the valid values on an unrecognized setting.
    """
    backend = os.environ.get(_BACKEND_ENV_VAR, _DEFAULT_BACKEND)
    if backend not in _VALID_BACKENDS:
        raise ValueError(
            f"Invalid {_BACKEND_ENV_VAR}={backend!r}. "
            f"Valid values: {sorted(_VALID_BACKENDS)}."
        )
    return backend
