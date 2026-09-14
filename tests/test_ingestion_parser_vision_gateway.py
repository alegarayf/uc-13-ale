"""Hermetic tests for _extract_figure_pages_with_vision's conditional gateway dispatch.

Derived from spec.md ASDK-09 (T21 "Done when") and AD-002 (STATE.md): like
company_profiler.call_llm() (T20), vision_endpoint is runtime-parametrized and
its own upstream code comment names a Llama vision model as a valid value, so
dispatch must check llm_client.is_claude_endpoint() before routing through the
gateway. Both branches pass the same OpenAI-style image_url block; on the
Claude branch, chat()'s own _call_anthropic() converts it internally via T6's
_to_anthropic_content() (covered by test_llm_client_vision.py) -- this call
site never converts anything itself.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

pytest.importorskip("fitz", reason="PyMuPDF required for vision extraction tests")

from jobs.scripts import ingestion_parser  # noqa: E402


def _make_one_page_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "chart placeholder")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def _pdf_path(tmp_path):
    p = tmp_path / "figures.pdf"
    p.write_bytes(_make_one_page_pdf())
    return str(p)


@patch("agents.shared.llm_client.chat")
def test_claude_vision_endpoint_routes_through_gateway_with_correct_arguments(
    mock_chat, _pdf_path
):
    mock_chat.return_value = ("Revenue: 100 | Growth: 12% | EBITDA Margin: 34% | Headcount: 250", {})

    chunks = ingestion_parser._extract_figure_pages_with_vision(
        file_path=_pdf_path,
        doc_id="doc1",
        file_name="figures.pdf",
        doc_title="Figures",
        figure_page_header_map={0: "Org Chart"},
        start_chunk_index=0,
        vision_endpoint="databricks-claude-haiku-4-5",
    )

    assert len(chunks) == 1
    assert "Revenue: 100" in chunks[0].chunk_text
    mock_chat.assert_called_once()
    kwargs = mock_chat.call_args.kwargs
    assert kwargs["endpoint"] == "databricks-claude-haiku-4-5"
    assert kwargs["max_tokens"] == 2000
    assert kwargs["temperature"] == 0.0
    # The call site passes the original OpenAI-style image_url block straight
    # into chat() -- the T6 conversion to Anthropic's {"type": "image", ...}
    # shape happens INSIDE chat()'s _call_anthropic(), not here (already
    # covered by test_llm_client_vision.py). This call site's only job is to
    # not convert anything itself.
    content = kwargs["user_content"]
    image_block = next(b for b in content if b["type"] == "image_url")
    url = image_block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1])  # decodes without error


@patch("agents.shared.llm_client.chat")
def test_llama_vision_endpoint_bypasses_the_gateway_entirely(mock_chat, _pdf_path):
    """The AD-002 case this test exists for: must not raise ValueError from
    resolve_model() on a documented-valid non-Claude vision_endpoint value."""
    with patch("mlflow.deployments.get_deploy_client") as mock_get_deploy:
        mock_client = MagicMock()
        mock_client.predict.return_value = {
            "choices": [{"message": {"content": "Revenue: 100 | Growth: 12% | EBITDA Margin: 34% | Headcount: 250"}}],
            "usage": {},
        }
        mock_get_deploy.return_value = mock_client

        chunks = ingestion_parser._extract_figure_pages_with_vision(
            file_path=_pdf_path,
            doc_id="doc1",
            file_name="figures.pdf",
            doc_title="Figures",
            figure_page_header_map={0: "Org Chart"},
            start_chunk_index=0,
            vision_endpoint="databricks-meta-llama-3-2-11b-vision-instruct",
        )

        assert len(chunks) == 1
        mock_chat.assert_not_called()
        mock_client.predict.assert_called_once()
        # Non-Claude branch must send the original image_url shape, unconverted.
        inputs = mock_client.predict.call_args.kwargs["inputs"]
        content = inputs["messages"][0]["content"]
        image_block = next(b for b in content if b["type"] == "image_url")
        assert image_block["image_url"]["url"].startswith("data:image/png;base64,")


@patch("agents.shared.llm_client.chat")
def test_no_data_response_produces_no_chunks_on_the_gateway_path(mock_chat, _pdf_path):
    mock_chat.return_value = ("NO_DATA", {})
    chunks = ingestion_parser._extract_figure_pages_with_vision(
        file_path=_pdf_path,
        doc_id="doc1",
        file_name="figures.pdf",
        doc_title="Figures",
        figure_page_header_map={0: "Org Chart"},
        start_chunk_index=0,
        vision_endpoint="databricks-claude-haiku-4-5",
    )
    assert chunks == []


def test_get_embeddings_batch_unaffected_by_the_vision_migration():
    """Confirms get_embeddings_batch still takes a caller-supplied client and
    never imports or touches llm_client -- an unrelated code path."""
    import inspect

    source = inspect.getsource(ingestion_parser.get_embeddings_batch)
    assert "llm_client" not in source
    params = inspect.signature(ingestion_parser.get_embeddings_batch).parameters
    assert "client" in params
