"""Capture a text clip into <inbox>/clips/<repo>/<uuid>.json with metadata,
and digest it into markdown under the store."""

import json
import os
import re
import socket
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from minne.reader import iter_session_files, project_dir_for_cwd
from minne.repo import resolve_repo


def _current_session_id(cwd: Path) -> str | None:
    """Best-effort: the JSONL with the most recent mtime in the project dir
    matching `cwd` is almost certainly the live session that invoked us."""
    pdir = project_dir_for_cwd(cwd)
    files = list(iter_session_files(pdir))
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime)
    return newest.stem


def _git_branch(cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        b = out.stdout.strip()
        return b if b and b != "HEAD" else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


_SLUG_NON = re.compile(r"[^a-z0-9]+")


def _hint_slug(source: str, text: str, limit: int = 40) -> str:
    """Short kebab-case hint for the clip filename.

    Uses the source file's stem if available, otherwise the first non-empty
    line of the text. Falls back to `clip` when nothing is usable."""
    if source and source != "stdin":
        base = Path(source).stem
    else:
        base = next((line.strip() for line in text.splitlines() if line.strip()), "")
    base = base.lower()[:120]
    slug = _SLUG_NON.sub("-", base).strip("-")[:limit].strip("-")
    return slug or "clip"


def add_clip(text: str, source: str, cwd: Path, inbox: Path) -> Path:
    repo = resolve_repo(str(cwd))
    out_dir = inbox / "clips" / repo
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_id = str(uuid.uuid4())
    envelope = {
        "id": clip_id,
        "type": "clip",
        "text": text,
        "source": source,
        "cwd": str(cwd),
        "repo": repo,
        "branch": _git_branch(cwd),
        "session_id": _current_session_id(cwd),
        "host": socket.gethostname(),
        "captured": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    hint = _hint_slug(source, text)
    out = out_dir / f"{hint}-{clip_id[:8]}.json"
    out.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return out


_SESSION_ID_RE = re.compile(r"^session_id:\s*(\S+)\s*$", re.MULTILINE)


def _index_chats_by_session(store: Path, repo: str) -> dict[str, Path]:
    """Map session_id → chat directory for digested chats in this repo.

    For nogit clips (repo == "_nogit"), search across all categories under
    `store/chats/nogit/<category>/<date>-<slug>/chat.md`."""
    if repo == "_nogit":
        repo_root = store / "chats" / "nogit"
        glob = "*/*/chat.md"
    else:
        repo_root = store / "chats" / repo
        glob = "*/chat.md"
    if not repo_root.is_dir():
        return {}
    index: dict[str, Path] = {}
    for chat in repo_root.glob(glob):
        try:
            head = chat.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if not head.startswith("---"):
            continue
        end = head.find("\n---", 3)
        if end < 0:
            continue
        m = _SESSION_ID_RE.search(head[:end])
        if m:
            index[m.group(1)] = chat.parent
    return index


def _render_clip_md(envelope: dict, chat_link: str | None) -> str:
    fm: list[str] = ["---"]
    for key in ("id", "captured", "source", "repo", "branch", "session_id", "host"):
        v = envelope.get(key)
        if v:
            fm.append(f"{key}: {v}")
    if chat_link:
        fm.append(f"chat: {chat_link}")
    fm.append("---")
    text = (envelope.get("text") or "").rstrip("\n")
    return "\n".join(fm) + "\n\n" + text + "\n"


def digest_clip(
    json_path: Path,
    store: Path,
    chat_index: dict[str, Path] | None = None,
) -> Path:
    """Render an inbox clip JSON to markdown under the store.

    If the clip's session_id matches a digested chat in this repo, the
    markdown lands at `store/chats/<repo>/<date>-<slug>/clips/<name>.md`
    with a relative link back to `chat.md`. Otherwise it lands at
    `store/clips/<repo>/<name>.md`. The source JSON is removed on success."""
    envelope = json.loads(json_path.read_text(encoding="utf-8"))
    repo = envelope.get("repo") or "unknown"
    session_id = envelope.get("session_id")

    if chat_index is None:
        chat_index = _index_chats_by_session(store, repo)
    chat_dir = chat_index.get(session_id) if session_id else None

    if chat_dir is not None:
        out_dir = chat_dir / "clips"
        chat_link = os.path.relpath(chat_dir / "chat.md", out_dir)
    else:
        out_dir = store / "clips" / repo
        chat_link = None

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{json_path.stem}.md"
    out.write_text(_render_clip_md(envelope, chat_link), encoding="utf-8")
    json_path.unlink()
    return out
