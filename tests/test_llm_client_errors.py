"""Hermetic tests for llm_client._is_retryable.

Derived from spec.md ASDK-05/ASDK-07 and design.md's Error Handling Strategy
table (T7 "Done when"). Uses real anthropic SDK exception instances (built
against a minimal httpx2.Response) rather than approximations, so the
isinstance checks in _is_retryable are exercised against the actual class
hierarchy -- RateLimitError, BadRequestError, etc. are all APIStatusError
subclasses, and the status-code boundary is what separates them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx2
import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

import anthropic  # noqa: E402

from agents.shared import llm_client  # noqa: E402

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, status_code: int):
    response = httpx2.Response(status_code, request=_REQUEST)
    return cls(f"status {status_code}", response=response, body=None)


# --- retryable: connection / timeout ----------------------------------------


def test_connection_error_is_retryable():
    assert llm_client._is_retryable(anthropic.APIConnectionError(request=_REQUEST)) is True


def test_timeout_error_is_retryable():
    assert llm_client._is_retryable(anthropic.APITimeoutError(request=_REQUEST)) is True


# --- retryable: exhausted rate limit -----------------------------------------


def test_rate_limit_error_is_retryable():
    exc = _status_error(anthropic.RateLimitError, 429)
    assert llm_client._is_retryable(exc) is True


# --- retryable: 5xx APIStatusError -------------------------------------------


@pytest.mark.parametrize("status_code", [500, 502, 503, 529])
def test_5xx_status_errors_are_retryable(status_code):
    exc = _status_error(anthropic.APIStatusError, status_code)
    assert llm_client._is_retryable(exc) is True


# --- NOT retryable: 4xx request errors ---------------------------------------


@pytest.mark.parametrize(
    ("cls", "status_code"),
    [
        (anthropic.BadRequestError, 400),
        (anthropic.AuthenticationError, 401),
        (anthropic.PermissionDeniedError, 403),
        (anthropic.NotFoundError, 404),
    ],
)
def test_4xx_request_errors_are_not_retryable(cls, status_code):
    exc = _status_error(cls, status_code)
    assert llm_client._is_retryable(exc) is False


# --- boundary: exactly 499 vs exactly 500 -----------------------------------


def test_status_499_is_not_retryable_boundary():
    exc = _status_error(anthropic.APIStatusError, 499)
    assert llm_client._is_retryable(exc) is False


def test_status_500_is_retryable_boundary():
    exc = _status_error(anthropic.APIStatusError, 500)
    assert llm_client._is_retryable(exc) is True


# --- unknown exception: NOT retryable (safer default) ------------------------


def test_unrecognized_exception_is_not_retryable():
    assert llm_client._is_retryable(ValueError("something else entirely")) is False
