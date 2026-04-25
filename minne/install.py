"""Install minne's bundled Claude Code skills into ~/.claude/skills/."""

import shutil
from importlib import resources
from pathlib import Path

SKILL_NAMES = ["minne"]


def install_skills(dest_root: Path | None = None) -> list[Path]:
    """Copy each bundled skill dir from minne/skills/<name>/ into
    <dest_root>/<name>/. Returns the list of installed dest dirs."""
    dest_root = dest_root or Path.home() / ".claude" / "skills"
    dest_root.mkdir(parents=True, exist_ok=True)

    installed: list[Path] = []
    for name in SKILL_NAMES:
        src = resources.files("minne.skills").joinpath(name)
        dest = dest_root / name
        with resources.as_file(src) as src_path:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src_path, dest)
        installed.append(dest)
    return installed
