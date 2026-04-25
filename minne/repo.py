"""Resolve a Claude Code project's cwd to a repo name for inbox grouping."""

import subprocess
from pathlib import Path

NOGIT = "_nogit"


def resolve_repo(cwd: str | None) -> str:
    """Return a short repo name for `cwd`. Returns the toplevel basename
    when `cwd` is inside a git work tree; otherwise the sentinel `_nogit`,
    which the digest pipeline then classifies into a topic category."""
    if not cwd:
        return NOGIT
    p = Path(cwd)
    if not p.is_dir():
        return NOGIT
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
    return NOGIT
