"""Resolve a Claude Code project's cwd to a repo name for inbox grouping."""

from pathlib import Path
import subprocess


UNKNOWN = "_unknown"


def resolve_repo(cwd: str | None) -> str:
    """Return a short repo name for `cwd`. Tries `git rev-parse --show-toplevel`
    when the directory exists; falls back to the cwd basename, or `_unknown`
    when the path is gone."""
    if not cwd:
        return UNKNOWN
    p = Path(cwd)
    if not p.is_dir():
        # path no longer exists; use basename as a hint
        return p.name or UNKNOWN
    try:
        out = subprocess.run(
            ["git", "-C", str(p), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
        top = out.stdout.strip()
        if top:
            return Path(top).name
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return p.name or UNKNOWN
