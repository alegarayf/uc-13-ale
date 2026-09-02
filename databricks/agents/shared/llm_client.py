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
import re
import threading

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


def _normalize_usage(usage) -> dict:
    """Convert an Anthropic `Usage` object to the shape the token counters expect.

    `usage` is the Pydantic model on `response.usage` (attribute access, e.g.
    `usage.input_tokens`) -- not a dict. Missing fields are treated as 0 rather
    than raising, matching the Databricks-serving path's tolerance for a
    partial `usage` payload. See agents/shared/agent_base.accumulate_tokens for
    the consumer of this shape.
    """
    prompt_tokens = getattr(usage, "input_tokens", None) or 0
    completion_tokens = getattr(usage, "output_tokens", None) or 0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


# Matches the data-URI shape jobs/scripts/ingestion_parser.py builds:
# f"data:image/png;base64,{img_b64}"
_DATA_URI_RE = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


def _to_anthropic_content(user_content: str | list[dict]) -> list[dict]:
    """Translate OpenAI-style content blocks to the Anthropic SDK's shape.

    A plain str is wrapped in a single text block. A list of blocks is
    translated element by element, preserving order: an "image_url" block with
    a base64 data-URI becomes {"type": "image", "source": {"type": "base64",
    "media_type": ..., "data": ...}}; "text" blocks pass through unchanged.
    Only the "databricks" backend path sends the original image_url shape --
    this conversion is Anthropic-only (ASDK-09 AC3).
    """
    if isinstance(user_content, str):
        return [{"type": "text", "text": user_content}]

    converted: list[dict] = []
    for block in user_content:
        block_type = block.get("type")
        if block_type == "image_url":
            url = block.get("image_url", {}).get("url", "")
            match = _DATA_URI_RE.match(url)
            if not match:
                raise ValueError(
                    f"Malformed image_url data-URI in vision block: {block!r}"
                )
            converted.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": match.group("media_type"),
                    "data": match.group("data"),
                },
            })
        else:
            converted.append(block)
    return converted


def _is_retryable(exc: Exception) -> bool:
    """True when `exc` justifies falling back to the Databricks serving path.

    Retryable: connection/timeout errors, an exhausted 429 (RateLimitError),
    and any 5xx APIStatusError. NOT retryable: BadRequestError (400),
    AuthenticationError (401), PermissionDeniedError (403), NotFoundError
    (404) -- these are all APIStatusError subclasses whose status_code is
    < 500, so the generic 5xx check below already excludes them without an
    explicit exclusion list. A bad key or an unmapped model should fail fast,
    not degrade silently for 200 calls (design.md Error Handling Strategy).
    Any exception this module doesn't recognize is treated as NOT retryable --
    degrading on an unknown failure mode is the riskier default.
    """
    import anthropic

    if isinstance(exc, anthropic.APIConnectionError):  # covers APITimeoutError too
        return True
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code >= 500
    return False


# --- Credential resolution and client construction --------------------------
#
# Duplicates the get_param()/get_secret()/_get_dbutils() pattern already used
# across agents/workstreams/*.py (e.g. financial_trends_agent.py:60-104) and
# jobs/scripts/check_anthropic_egress.py. Not refactored into one shared
# helper -- design.md Risk C-2 registers that as deliberate, pre-existing debt
# out of scope for this migration.

_SECRET_KEY = "anthropic_api_key"
_ENV_VAR = "ANTHROPIC_API_KEY"

_client_lock = threading.Lock()
_client_state: dict = {"client": None}


def _get_dbutils():
    """Return dbutils when running inside a Databricks notebook, else None."""
    try:
        import IPython

        return IPython.get_ipython().user_ns.get("dbutils")
    except Exception:
        return None


def get_param(key: str, default: str | None = None) -> str | None:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            value = _dbutils.widgets.get(key)
            if value:
                return value
        except Exception:
            pass
    return os.environ.get(key, default)


def _resolve_api_key() -> str:
    """Read the Anthropic API key from the secret scope, falling back to env.

    Never includes the key value in the raised message -- only the names of
    the places consulted (ASDK-08 AC2/AC4).
    """
    scope = get_param("anthropic_secret_scope", default="uc13")
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            value = _dbutils.secrets.get(scope, _SECRET_KEY)
            if value:
                return value
        except Exception:
            pass
    value = os.environ.get(_ENV_VAR)
    if value:
        return value
    raise RuntimeError(
        f"Anthropic API key not found. On Databricks: add '{_SECRET_KEY}' to "
        f"the '{scope}' secret scope. Locally: export {_ENV_VAR}."
    )


def _get_anthropic_client():
    """Build the Anthropic client lazily, once per process, under a lock.

    A 600s timeout with the SDK's own retry logic (max_retries=2) replaces the
    ~120s serving read-timeout ceiling that forced BMA's two-pass split (C37).
    Guarded by threading.Lock because pipeline.py runs agents concurrently via
    ThreadPoolExecutor (design.md edge case) -- without it, two threads racing
    on first use could construct two clients.

    Raises ImportError (not degrading to Databricks) when the `anthropic`
    package itself is missing -- a missing dependency is a deployment defect,
    not a transient failure the fallback should paper over.
    """
    with _client_lock:
        if _client_state["client"] is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ImportError(
                    "The 'anthropic' package is required for LLM_BACKEND="
                    "'anthropic'. Install it with: pip install anthropic>=1.3.0"
                ) from exc
            api_key = _resolve_api_key()
            _client_state["client"] = anthropic.Anthropic(
                api_key=api_key, timeout=600, max_retries=2
            )
        return _client_state["client"]


# --- Databricks serving path (fallback + LLM_BACKEND=databricks) ------------

_databricks_client_lock = threading.Lock()
_databricks_client_state: dict = {"client": None}


def _get_databricks_client():
    """Build the MLflow deploy client lazily, once per process, under a lock.

    Mirrors agent_base.WorkstreamAgent._get_llm_client's timeout override:
    the deploy client's HTTP read timeout defaults to 120s
    (MLFLOW_HTTP_REQUEST_TIMEOUT), which is too short for a 12-16K-token
    generation. Assigning 1800s (not setdefault) ensures a cluster-preset
    value can't win.
    """
    with _databricks_client_lock:
        if _databricks_client_state["client"] is None:
            import mlflow.deployments

            os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] = "1800"
            os.environ["DATABRICKS_HTTP_TIMEOUT"] = "1800"
            _databricks_client_state["client"] = mlflow.deployments.get_deploy_client(
                "databricks"
            )
        return _databricks_client_state["client"]


def _call_anthropic(
    *,
    system_prompt: str | None,
    user_content: str | list[dict],
    model_id: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict]:
    """Call the Anthropic SDK. Returns (text, usage) in the counter shape.

    stop_reason == "max_tokens" returns the partial text as-is (no special
    handling needed -- whatever text accumulated in the response is returned,
    matching the serving path's behavior so
    agent_base._recover_truncated_json() keeps working unchanged).
    stop_reason == "refusal" raises, naming the refusal category, rather than
    returning empty text the JSON parser would misread as a corrupt response.
    """
    client = _get_anthropic_client()
    content = _to_anthropic_content(user_content)
    kwargs = {"system": system_prompt} if system_prompt is not None else {}
    response = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": content}],
        **kwargs,
    )

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise RuntimeError(
            f"Anthropic refused the request (stop_details.category={category!r})."
        )

    text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text = block.text
            break
    if not text:
        print("  ⚠ Anthropic response contained no text block.")

    return text, _normalize_usage(response.usage)


def _call_databricks(
    *,
    system_prompt: str | None,
    user_content: str | list[dict],
    endpoint: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict]:
    """Call the Databricks Model Serving endpoint. Returns (text, usage).

    Sends `user_content` unmodified -- including a vision block list in its
    original "image_url" shape (ASDK-09 AC3). This is the exact predict() body
    already used by agent_base._call_llm and the eight narrative call sites,
    now shared instead of duplicated.
    """
    client = _get_databricks_client()
    messages = []
    if system_prompt is not None:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    response = client.predict(
        endpoint=endpoint,
        inputs={
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
    )
    text = response["choices"][0]["message"]["content"]
    return text, response.get("usage", {})


# --- Fallback bookkeeping ----------------------------------------------------
#
# Mirrors the threading.Lock-guarded counter pattern in
# agent_base.py's _token_lock / _token_totals.

_fallback_lock = threading.Lock()
_fallback_count = 0


def get_fallback_count() -> int:
    """Number of Anthropic-to-Databricks degradations so far this run."""
    with _fallback_lock:
        return _fallback_count


def reset_fallback_count() -> None:
    """Reset the degradation counter. Call alongside agent_base.reset_token_counter()."""
    global _fallback_count
    with _fallback_lock:
        _fallback_count = 0


# Per-endpoint "which backend actually served the most recent call" -- ASDK-11
# AC3 needs the resolved backend per endpoint, not the LLM_BACKEND setting.
# LLM_BACKEND never changes mid-run, so reading _active_backend() at report
# time would still say "anthropic" for an endpoint that degraded to
# Databricks on every call. This is scoped state chat() already computes
# (the same `backend` value it sets on the MLflow span); recording it here is
# what makes the report accurate instead of an approximation.
_endpoint_backend_lock = threading.Lock()
_endpoint_backends: dict = {}


def get_endpoint_backends() -> dict:
    """Copy of {endpoint_alias: backend} for the backend that served each
    endpoint's most recent call."""
    with _endpoint_backend_lock:
        return dict(_endpoint_backends)


def reset_endpoint_backends() -> None:
    """Reset the per-endpoint backend record. Call alongside reset_fallback_count()."""
    with _endpoint_backend_lock:
        _endpoint_backends.clear()


def _record_endpoint_backend(endpoint: str, backend: str) -> None:
    with _endpoint_backend_lock:
        _endpoint_backends[endpoint] = backend


def _record_fallback(endpoint: str, exc: Exception) -> None:
    global _fallback_count
    with _fallback_lock:
        _fallback_count += 1
    print(f"  [llm_fallback] {endpoint}: {type(exc).__name__}: {exc}")


def _resolved_backend(fallback_occurred: bool) -> str:
    """The backend that actually served (or attempted to serve) a call.

    "databricks" when a fallback occurred, or when LLM_BACKEND itself is set
    to "databricks"; "anthropic" otherwise.
    """
    return "databricks" if (fallback_occurred or _active_backend() != "anthropic") else "anthropic"


def _route_and_maybe_fallback(
    *,
    system_prompt: str | None,
    user_content: str | list[dict],
    endpoint: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict, bool]:
    """Route to a backend, falling back once on a retryable Anthropic failure.

    Returns (text, usage, fallback_used). fallback_used is a value returned
    from this specific call, not derived from a diff on the shared
    _fallback_count counter -- pipeline.py runs agents concurrently via
    ThreadPoolExecutor, so a counter-diff approach would attribute another
    thread's fallback to this call under a race.

    On the "anthropic" backend, a transient failure (per _is_retryable)
    degrades once to the Databricks serving endpoint of the same alias and
    logs it with the "[llm_fallback]" marker; a non-retryable failure (a bad
    key, an unmapped model, a policy refusal) propagates immediately instead
    of silently falling back. If the Databricks fallback itself fails, that
    exception propagates with the original Anthropic exception chained as its
    cause (`raise ... from ...`). There is no retry loop between backends --
    at most one degradation per call.
    """
    if _active_backend() != "anthropic":
        text, usage = _call_databricks(
            system_prompt=system_prompt,
            user_content=user_content,
            endpoint=endpoint,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return text, usage, False

    model_id = resolve_model(endpoint)
    try:
        text, usage = _call_anthropic(
            system_prompt=system_prompt,
            user_content=user_content,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return text, usage, False
    except Exception as exc:
        if not _is_retryable(exc):
            raise
        _record_fallback(endpoint, exc)
        try:
            text, usage = _call_databricks(
                system_prompt=system_prompt,
                user_content=user_content,
                endpoint=endpoint,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as databricks_exc:
            raise databricks_exc from exc
        return text, usage, True


# --- MLflow instrumentation ---------------------------------------------------
#
# Manual spans are the PRIMARY tracing mechanism -- not mlflow.anthropic.autolog().
# Two reasons, both confirmed rather than assumed (design.md R-1, and the
# ASDK-13 egress gate on 2026-09-01): MLflow's autolog is only tested against
# anthropic 0.55.0-0.107.1, while this project runs 1.3.0 (outside that
# range -- autolog is inert in this environment, not hypothetically); and
# autolog only instruments the Anthropic SDK call itself, so it would produce
# no trace at all for a call that degraded to Databricks -- exactly the call
# most worth seeing. Autolog is enabled only as an opportunistic enrichment
# when the installed version happens to support it.

_AUTOLOG_MIN = (0, 55, 0)
_AUTOLOG_MAX = (0, 107, 1)
_autolog_state: dict = {"attempted": False}


def _parse_version(raw: str) -> tuple[int, ...]:
    """Parse a dotted version into a comparable tuple, ignoring suffixes."""
    parts: list[int] = []
    for chunk in raw.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _autolog_version_supported(version: str) -> bool:
    """True when `version` falls inside MLflow's autolog-tested range."""
    parsed = _parse_version(version)
    if not parsed:
        return False
    padded = parsed + (0,) * (3 - len(parsed)) if len(parsed) < 3 else parsed[:3]
    return _AUTOLOG_MIN <= padded <= _AUTOLOG_MAX


def _maybe_enable_autolog() -> None:
    """Enable mlflow.anthropic.autolog() once, only if the SDK version supports it."""
    if _autolog_state["attempted"]:
        return
    _autolog_state["attempted"] = True
    try:
        import anthropic

        version = getattr(anthropic, "__version__", "")
        if not _autolog_version_supported(version):
            print(
                f"  ⚠ Skipping mlflow.anthropic.autolog(): anthropic {version!r} "
                f"is outside the tested range 0.55.0-0.107.1. Manual gateway "
                f"spans remain the tracing mechanism."
            )
            return
        import mlflow.anthropic

        mlflow.anthropic.autolog()
    except Exception as exc:
        print(
            f"  ⚠ Could not enable mlflow.anthropic.autolog(): "
            f"{type(exc).__name__}: {exc}"
        )


def _try_open_span():
    """Open an MLflow span for one chat() call, or (None, None) if unavailable.

    Any failure importing mlflow, calling start_span(), or entering the
    context manager is treated the same way: log a warning and let the caller
    proceed without tracing. Tracing must never block a model call.
    """
    try:
        import mlflow

        span_cm = mlflow.start_span(name="llm_client.chat")
        span = span_cm.__enter__()
        return span, span_cm
    except Exception as exc:
        print(
            f"  ⚠ MLflow tracing unavailable, continuing without a span: "
            f"{type(exc).__name__}: {exc}"
        )
        return None, None


def _safe_set_span_attributes(
    span, *, endpoint: str, max_tokens: int, fallback_used: bool, backend: str, usage: dict | None
) -> None:
    """Set span attributes, never letting a tracing failure surface to the caller.

    The API key never appears here -- only the endpoint alias, resolved
    backend, fallback flag, max_tokens, and token counts.
    """
    try:
        attributes = {
            "llm.endpoint_alias": endpoint,
            "llm.backend": backend,
            "llm.fallback_used": fallback_used,
            "llm.max_tokens": max_tokens,
        }
        if usage is not None:
            attributes["llm.prompt_tokens"] = usage.get("prompt_tokens", 0)
            attributes["llm.completion_tokens"] = usage.get("completion_tokens", 0)
        span.set_attributes(attributes)
    except Exception as exc:
        print(f"  ⚠ Could not set MLflow span attributes: {type(exc).__name__}: {exc}")


def chat(
    *,
    system_prompt: str | None,
    user_content: str | list[dict],
    endpoint: str,
    max_tokens: int,
    temperature: float = 0.0,
) -> tuple[str, dict]:
    """Route a single chat/vision call to whichever backend LLM_BACKEND selects.

    `endpoint` is the Databricks-style alias every call site already passes
    (e.g. "databricks-claude-sonnet-4-6") -- unchanged from today, so no
    workflow YAML, widget default, or notebook needs to change. See
    _route_and_maybe_fallback for the backend/fallback contract.

    Every call opens an MLflow span (nested under whatever span is already
    active, e.g. pipeline.py's `agent::{key}`) recording the endpoint alias,
    resolved backend, fallback flag, max_tokens, and token usage -- unless
    MLflow itself is unavailable, in which case the call still completes.
    Recording which backend served `endpoint` (for get_endpoint_backends(),
    consumed by agent_base.print_token_summary()) happens independently of
    whether tracing succeeded -- it must not go stale just because MLflow was
    unavailable for this call.
    """
    _maybe_enable_autolog()

    span, span_cm = _try_open_span()
    if span is None:
        text, usage, fallback_used = _route_and_maybe_fallback(
            system_prompt=system_prompt,
            user_content=user_content,
            endpoint=endpoint,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        _record_endpoint_backend(endpoint, _resolved_backend(fallback_used))
        return text, usage

    try:
        text, usage, fallback_used = _route_and_maybe_fallback(
            system_prompt=system_prompt,
            user_content=user_content,
            endpoint=endpoint,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except BaseException as exc:
        # exc.__cause__ is set only when _route_and_maybe_fallback attempted
        # the Databricks fallback and it also failed (`raise ... from exc`).
        # A non-retryable failure re-raises bare, leaving __cause__ None. This
        # is call-local and race-free, unlike diffing the shared counter.
        fallback_attempted = exc.__cause__ is not None
        backend = _resolved_backend(fallback_attempted)
        _record_endpoint_backend(endpoint, backend)
        _safe_set_span_attributes(
            span, endpoint=endpoint, max_tokens=max_tokens,
            fallback_used=fallback_attempted, backend=backend, usage=None,
        )
        try:
            span_cm.__exit__(type(exc), exc, exc.__traceback__)
        except Exception:
            pass
        raise

    backend = _resolved_backend(fallback_used)
    _record_endpoint_backend(endpoint, backend)
    _safe_set_span_attributes(
        span, endpoint=endpoint, max_tokens=max_tokens,
        fallback_used=fallback_used, backend=backend, usage=usage,
    )
    try:
        span_cm.__exit__(None, None, None)
    except Exception as exc:
        print(f"  ⚠ MLflow span exit failed: {type(exc).__name__}: {exc}")
    return text, usage
