"""Capture a text clip into <inbox>/clips/<repo>/<uuid>.json with metadata."""

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import socket
import subprocess
import uuid

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
            check=True, capture_output=True, text=True,
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
        "captured": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    hint = _hint_slug(source, text)
    out = out_dir / f"{hint}-{clip_id[:8]}.json"
    out.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return out
