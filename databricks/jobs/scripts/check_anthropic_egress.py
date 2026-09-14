"""ASDK-13 / ASDK-15 gate: can this Databricks runtime reach the Anthropic API?

Run this as a serverless task BEFORE migrating any production call site. It
answers three questions that only the cluster can answer:

  1. Does ``import anthropic`` succeed, or does it collide with the transitive
     dependencies already installed (``anthropic`` 1.x runs on ``httpx2``)?
  2. Is there network egress from the job to ``api.anthropic.com``?
  3. Is the installed SDK version inside the range MLflow's
     ``mlflow.anthropic.autolog()`` is tested against?

Deliberately standalone: it does not import ``agents.shared.llm_client``,
because it runs before that module exists. The credential lookup below is a
temporary duplicate of the pattern the gateway will own from T8 onward.

Observable stdout contract (these substrings are binding -- the signoff greps
for them, so do not reword them):

  ANTHROPIC_IMPORT_FAILED <type>: <msg>      import collided; exit 1
  ANTHROPIC_SDK_VERSION <v> autolog_supported=<bool>
  ANTHROPIC_EGRESS_OK <model_id>             call succeeded
  ANTHROPIC_EGRESS_BLOCKED <model_id> ...    no network path; exit 1
  ANTHROPIC_EGRESS_REACHABLE <model_id> ...  API answered with an error status

SPEC_DEVIATION: spec.md ASDK-13 AC2 defines only EGRESS_BLOCKED for a failed
call. An HTTP error status (401 bad key, 404 unknown model) proves egress
WORKS -- reporting it as BLOCKED would invert the one fact this gate exists to
establish. ANTHROPIC_EGRESS_REACHABLE separates "network is open, call failed"
from "network is closed". Both still exit non-zero.
Reason: the spec does not define an outcome for this case (spec-precision gap).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Model IDs mirror the alias table the gateway will own (design.md
# "Contrato de traducción"). Verifying both here is what confirms that
# assumption against a live API instead of against a naming convention.
_MODEL_IDS = ("claude-sonnet-4-6", "claude-haiku-4-5")

# Range MLflow documents as tested for mlflow.anthropic.autolog().
_AUTOLOG_MIN = (0, 55, 0)
_AUTOLOG_MAX = (0, 107, 1)

_SECRET_KEY = "anthropic_api_key"
_ENV_VAR = "ANTHROPIC_API_KEY"


def _get_dbutils():
    """Return dbutils when running inside Databricks, else None."""
    try:
        import IPython

        return IPython.get_ipython().user_ns.get("dbutils")
    except Exception:
        return None


def _load_dotenv_if_local() -> None:
    """Load databricks/.env when running off-cluster.

    Mirrors the helper the production modules already use (see
    financial_trends_agent._load_dotenv_if_local). Without it, a local run only
    sees an exported env var, so the key sitting in databricks/.env is ignored
    and the gate reports a missing credential that is actually present.
    """
    if _get_dbutils() is not None:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


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
    """Read the API key from the secret scope, falling back to the env var.

    Never includes a secret value in the raised message -- only the names of
    the places that were consulted.
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


def _parse_version(raw: str) -> tuple[int, ...]:
    """Parse a dotted version into a comparable tuple, ignoring suffixes.

    Returns an empty tuple when no leading numeric component is present, which
    callers treat as "unknown" rather than guessing a value.
    """
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


def autolog_supported(version: str) -> bool:
    """True when `version` falls inside MLflow's tested autolog range."""
    parsed = _parse_version(version)
    if not parsed:
        return False
    padded = parsed + (0,) * (3 - len(parsed)) if len(parsed) < 3 else parsed[:3]
    return _AUTOLOG_MIN <= padded <= _AUTOLOG_MAX


def _import_anthropic():
    """Import the SDK. Split out so tests can simulate a collision."""
    import anthropic

    return anthropic


def main() -> int:
    _load_dotenv_if_local()
    try:
        anthropic = _import_anthropic()
    except Exception as exc:  # noqa: BLE001 - any import failure is the signal
        print(f"ANTHROPIC_IMPORT_FAILED {type(exc).__name__}: {exc}")
        return 1

    version = getattr(anthropic, "__version__", "unknown")
    print(
        f"ANTHROPIC_SDK_VERSION {version} "
        f"autolog_supported={autolog_supported(version)}"
    )

    try:
        api_key = _resolve_api_key()
    except RuntimeError as exc:
        print(f"ANTHROPIC_CREDENTIAL_MISSING {exc}")
        return 1

    # max_retries=0 so a network block surfaces immediately instead of being
    # retried into a timeout -- this is a probe, not a production call.
    client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=0)

    failures = 0
    for model_id in _MODEL_IDS:
        try:
            client.messages.create(
                model=model_id,
                max_tokens=16,
                messages=[{"role": "user", "content": "Reply with: ok"}],
            )
            print(f"ANTHROPIC_EGRESS_OK {model_id}")
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
            print(f"ANTHROPIC_EGRESS_BLOCKED {model_id} {type(exc).__name__}: {exc}")
            failures += 1
        except anthropic.APIStatusError as exc:
            print(
                f"ANTHROPIC_EGRESS_REACHABLE {model_id} "
                f"status={exc.status_code} {type(exc).__name__}: {exc}"
            )
            failures += 1
        except Exception as exc:  # noqa: BLE001 - unknown failure is still a failure
            print(f"ANTHROPIC_EGRESS_BLOCKED {model_id} {type(exc).__name__}: {exc}")
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
