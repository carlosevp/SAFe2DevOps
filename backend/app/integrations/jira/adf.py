from __future__ import annotations

from typing import Any


def adf_to_plain_text(value: Any) -> str:
    """Convert Atlassian Document Format (or plain strings) to bounded plain text.

    Handles None, strings, dicts, lists, text nodes, paragraphs, hard breaks, and
    unknown nodes without raising. Unsupported structured values yield empty text
    rather than a Python repr.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [adf_to_plain_text(item) for item in value]
        return "".join(part for part in parts if part)
    if not isinstance(value, dict):
        return ""

    node_type = value.get("type")
    if node_type == "text":
        text = value.get("text")
        return text if isinstance(text, str) else ""
    if node_type == "hardBreak":
        return "\n"
    if node_type == "emoji":
        short = value.get("shortName") or value.get("text")
        return short if isinstance(short, str) else ""
    if node_type == "mention":
        text = value.get("text")
        return text if isinstance(text, str) else ""
    if node_type == "inlineCard":
        attrs = value.get("attrs") if isinstance(value.get("attrs"), dict) else {}
        url = attrs.get("url")
        return url if isinstance(url, str) else ""

    content = value.get("content")
    if not isinstance(content, list):
        return ""

    inner = "".join(adf_to_plain_text(child) for child in content)
    if node_type in {"paragraph", "heading", "blockquote", "listItem", "codeBlock", "panel"}:
        return inner.rstrip("\n") + "\n"
    if node_type in {"bulletList", "orderedList", "doc", "table", "tableRow", "tableCell"}:
        return inner
    return inner
