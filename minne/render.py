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


def _front_matter(records: list[dict]) -> str:
    cwds: list[str] = []
    seen: set[str] = set()
    session_id = ""
    first_ts = ""
    last_ts = ""
    for r in records:
        cwd = r.get("cwd")
        if isinstance(cwd, str) and cwd not in seen:
            seen.add(cwd)
            cwds.append(cwd)
        sid = r.get("sessionId")
        if isinstance(sid, str) and not session_id:
            session_id = sid
        ts = r.get("timestamp")
        if isinstance(ts, str):
            if not first_ts:
                first_ts = ts
            last_ts = ts

    lines = ["---"]
    if session_id:
        lines.append(f"session_id: {session_id}")
    if first_ts:
        lines.append(f"started: {first_ts}")
    if last_ts and last_ts != first_ts:
        lines.append(f"ended: {last_ts}")
    if len(cwds) == 1:
        lines.append(f"cwd: {cwds[0]}")
    elif len(cwds) > 1:
        lines.append("cwds:")
        for c in cwds:
            lines.append(f"  - {c}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def render_session(records: Iterable[dict]) -> str:
    """Render a session's records as markdown, keeping only user/assistant text."""
    records = list(records)
    parts: list[str] = []
    current_cwd: str | None = None
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
        cwd = r.get("cwd") if isinstance(r.get("cwd"), str) else None
        if cwd and cwd != current_cwd:
            if current_cwd is not None:
                parts.append(f"> cwd changed to `{cwd}`")
            current_cwd = cwd
        parts.append(f"## {t}\n\n" + "\n\n".join(texts))
    if not parts:
        return ""
    return _front_matter(records) + "\n" + "\n\n".join(parts) + "\n"
