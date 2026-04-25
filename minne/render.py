"""Render Claude Code JSONL records into markdown."""

from collections.abc import Iterable


def _extract_text_blocks(content: object) -> list[str]:
    """Pull only `text` blocks from a message's content. Drop tool_use,
    tool_result, thinking, and other structural blocks."""
    if isinstance(content, str):
        return [content] if content.strip() else []
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            text = c.get("text") or ""
            if text.strip():
                out.append(text)
    return out


def render_session(records: Iterable[dict]) -> str:
    """Render a session's records as markdown, keeping only user/assistant text."""
    parts: list[str] = []
    for r in records:
        t = r.get("type")
        if t not in ("user", "assistant"):
            continue
        if r.get("isMeta"):
            continue
        msg = r.get("message") or {}
        content = msg.get("content", r.get("content"))
        texts = _extract_text_blocks(content)
        if not texts:
            continue
        parts.append(f"## {t}\n\n" + "\n\n".join(texts))
    return "\n\n".join(parts) + "\n" if parts else ""
