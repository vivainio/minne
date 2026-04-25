"""Tolerant reader for Claude Code conversation JSONL files.

Claude Code stores one JSONL file per session under
``~/.claude/projects/<encoded-cwd>/<session-id>.jsonl``. The encoding replaces
``/`` and ``.`` with ``-`` (e.g. ``/home/v/.claude`` -> ``-home-v--claude``).

The schema is undocumented and changes; everything here parses defensively.
"""

import json
import os
from collections.abc import Iterator
from pathlib import Path


def encode_cwd(cwd: Path) -> str:
    """Slugify an absolute path the way Claude Code names project dirs."""
    s = str(cwd.resolve())
    return s.replace("/", "-").replace(".", "-")


def projects_root() -> Path:
    return Path(os.path.expanduser("~/.claude/projects"))


def project_dir_for_cwd(cwd: Path | None = None) -> Path:
    return projects_root() / encode_cwd(cwd or Path.cwd())


def iter_session_files(project_dir: Path) -> Iterator[Path]:
    if not project_dir.is_dir():
        return
    yield from sorted(project_dir.glob("*.jsonl"))


def iter_records(path: Path) -> Iterator[dict]:
    """Yield parsed JSON objects from a JSONL file, skipping malformed lines."""
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj
