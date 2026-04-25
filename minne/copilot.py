"""Reader for GitHub Copilot CLI sessions.

Copilot CLI stores per-session state under ``~/.copilot/session-state/<sid>/``
with an ``events.jsonl`` log and a small ``workspace.yaml`` carrying
``cwd``/``created_at``/``updated_at``. We render only ``user.message`` and
``assistant.message`` events, producing the same markdown transcript shape
Claude Code transcripts use so the rest of the digest pipeline runs
unchanged."""

import json
import os
from collections.abc import Iterator
from pathlib import Path


def copilot_root() -> Path:
    return Path(os.path.expanduser("~/.copilot/session-state"))


def iter_session_dirs(root: Path | None = None) -> Iterator[Path]:
    r = root or copilot_root()
    if not r.is_dir():
        return
    yield from sorted(p for p in r.iterdir() if p.is_dir())


def _iter_events(session_dir: Path) -> Iterator[dict]:
    f = session_dir / "events.jsonl"
    if not f.is_file():
        return
    with f.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def _parse_workspace(session_dir: Path) -> dict[str, str]:
    """Lightweight workspace.yaml parser — tolerates the Copilot-specific
    flat key:value format without pulling in PyYAML."""
    out: dict[str, str] = {}
    f = session_dir / "workspace.yaml"
    if not f.is_file():
        return out
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line or line.startswith(" ") or line.startswith("\t"):
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip("\"'")
    return out


def session_mtime(session_dir: Path) -> float:
    f = session_dir / "events.jsonl"
    target = f if f.is_file() else session_dir
    try:
        return target.stat().st_mtime
    except OSError:
        return 0.0


def render_session(session_dir: Path) -> str:
    """Return a markdown transcript for a Copilot session, or '' if there
    are no user/assistant messages."""
    sid = session_dir.name
    ws = _parse_workspace(session_dir)
    cwd = ws.get("cwd", "")
    started = ws.get("created_at", "")
    ended = ws.get("updated_at", "")

    parts: list[str] = []
    for ev in _iter_events(session_dir):
        t = ev.get("type")
        data = ev.get("data") or {}
        if t == "user.message":
            content = data.get("content") or ""
            if content.strip():
                parts.append(f"## user\n\n{content.strip()}")
        elif t == "assistant.message":
            content = data.get("content") or ""
            if content.strip():
                parts.append(f"## assistant\n\n{content.strip()}")

    if not parts:
        return ""

    fm = ["---", f"session_id: {sid}", "producer: copilot-cli"]
    if started:
        fm.append(f"started: {started}")
    if ended and ended != started:
        fm.append(f"ended: {ended}")
    if cwd:
        fm.append(f"cwd: {cwd}")
    fm.append("---")
    return "\n".join(fm) + "\n\n" + "\n\n".join(parts) + "\n"


def session_cwd(session_dir: Path) -> str | None:
    return _parse_workspace(session_dir).get("cwd") or None
