import re

from databricks.sdk.service.dashboards import GenieMessage


class GenieMessageError(ValueError):
    pass


def extract_genie_response_text(message: GenieMessage) -> str:
    """
    Return Genie's AI-generated reply text.

    `message.content` is typically the user's question, not the answer.
    The answer lives in `attachments[].text.content`.
    """
    texts: list[str] = []
    for att in message.attachments or []:
        if att.text and att.text.content:
            chunk = att.text.content.strip()
            if chunk:
                texts.append(chunk)

    if texts:
        return max(texts, key=len)

    raise GenieMessageError(
        "Genie did not return a text attachment. The space may have answered with SQL only."
    )


_QUESTION_LINE = re.compile(
    r"^\s*(?:would you|could you|can you|please (?:confirm|clarify|provide|let me know)|"
    r"which |what (?:field|metric|value)|do you want|let me know|"
    r"is there\b|are there\b|should i\b).*\?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def sanitize_summary_text(text: str) -> str:
    """Drop chatbot-style question lines; keep declarative understanding only."""
    lines = [line for line in text.splitlines() if not _QUESTION_LINE.match(line)]
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned or text.strip()


def display_summary_from_genie_text(genie_text: str) -> str:
    """Plain-language summary for the UI (hide embedded JSON blocks)."""
    without_fences = re.sub(r"```(?:json)?\s*\n?[\s\S]*?\n?```", "", genie_text, flags=re.IGNORECASE)
    without_json = re.sub(r"^\s*\{[\s\S]*?\}\s*", "", without_fences.strip(), count=1).strip()
    cleaned = without_json if len(without_json) >= 20 else genie_text.strip()
    cleaned = sanitize_summary_text(cleaned)
    if len(cleaned) > 2000:
        return cleaned[:1997].rstrip() + "…"
    return cleaned
