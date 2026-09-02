"""Confirms document_classifier.classify_batch() is deliberately NOT migrated.

Derived from spec.md's Out of Scope table (T19 finding, 2026-09-02).
_CLASSIFIER_ENDPOINT is "databricks-meta-llama-3-3-70b-instruct" -- Llama, not
Claude. Routing it through llm_client.chat() would raise ValueError on every
call (resolve_model() has no entry for a Llama alias), breaking document
classification in production. This test makes that exclusion an explicit,
permanent assertion rather than an artifact of the static convention scan
(T22) only happening to skip it because its endpoint string lacks "claude".

If this test ever fails because someone points the classifier at a Claude
endpoint, that is a deliberate model change requiring its own migration and
quality validation -- not something to route through llm_client by default.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from jobs.scripts import document_classifier  # noqa: E402


def test_classify_batch_still_calls_the_raw_deploy_client_not_the_gateway():
    """Routing this through llm_client would raise ValueError on the Llama
    alias -- verify the deploy client path is still the one exercised."""
    mock_client = MagicMock()
    mock_client.predict.return_value = {
        "choices": [{"message": {"content": "[]"}}],
        "usage": {},
    }
    with patch("agents.shared.llm_client.chat") as mock_chat:
        document_classifier.classify_batch(
            files_batch=[{"file_name": "a.pdf", "relative_path": "a.pdf", "folder_path": ""}],
            client=mock_client,
            upload_signals={},
        )
        mock_chat.assert_not_called()

    endpoint_used = mock_client.predict.call_args.kwargs["endpoint"]
    assert endpoint_used == "databricks-meta-llama-3-3-70b-instruct"
    assert "claude" not in endpoint_used
