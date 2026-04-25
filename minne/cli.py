import argparse
import os
import re
from collections import Counter
from pathlib import Path

from minne.install import install_skills
from minne.reader import iter_records, iter_session_files, project_dir_for_cwd, projects_root
from minne.render import render_session
from minne.repo import resolve_repo
from minne.summarize import summarize_file


def default_inbox() -> Path:
    return Path(os.environ.get("MINNE_HOME", str(Path.home() / "minne"))) / "inbox"


def cmd_scan(args: argparse.Namespace) -> None:
    pdir = project_dir_for_cwd(args.cwd)
    print(f"project dir: {pdir}")
    files = list(iter_session_files(pdir))
    print(f"sessions: {len(files)}")
    for f in files:
        counts: Counter[str] = Counter()
        total = 0
        for rec in iter_records(f):
            counts[rec.get("type", "?")] += 1
            total += 1
        summary = ", ".join(f"{k}={v}" for k, v in counts.most_common())
        print(f"  {f.name}  ({total} records)  {summary}")


def _existing_by_session_id(inbox: Path) -> dict[str, Path]:
    """Map session_id -> existing transcript path, walking the inbox tree."""
    out: dict[str, Path] = {}
    for p in inbox.rglob("*.md"):
        if p.name.endswith(".summary.md"):
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:512]
        except OSError:
            continue
        m = re.search(r"^session_id:\s*(\S+)", head, re.MULTILINE)
        if m:
            out[m.group(1)] = p
    return out


def _first_cwd(records: list[dict]) -> str | None:
    for r in records:
        cwd = r.get("cwd")
        if isinstance(cwd, str):
            return cwd
    return None


def _project_dirs(args: argparse.Namespace) -> list[Path]:
    if args.cwd is not None:
        return [project_dir_for_cwd(args.cwd)]
    root = projects_root()
    return sorted([d for d in root.iterdir() if d.is_dir()]) if root.is_dir() else []


def cmd_ingest(args: argparse.Namespace) -> None:
    inbox: Path = args.inbox
    inbox.mkdir(parents=True, exist_ok=True)
    existing = _existing_by_session_id(inbox)
    written = 0
    skipped = 0
    for pdir in _project_dirs(args):
        for f in iter_session_files(pdir):
            session_id = f.stem
            records = list(iter_records(f))
            md = render_session(records)
            if not md:
                skipped += 1
                continue
            if session_id in existing:
                out = existing[session_id]
            else:
                repo = resolve_repo(_first_cwd(records))
                repo_dir = inbox / repo
                repo_dir.mkdir(parents=True, exist_ok=True)
                out = repo_dir / f"{session_id}.md"
            out.write_text(md, encoding="utf-8")
            print(f"  wrote {out}  ({len(md)} bytes)")
            written += 1
    print(f"done: {written} written, {skipped} empty, into {inbox}")


def cmd_summarize(args: argparse.Namespace) -> None:
    target: Path = args.path
    if target.is_file():
        targets = [target]
    else:
        mds = sorted(target.rglob("*.md"), key=lambda p: p.stat().st_mtime)
        targets = [p for p in mds if not p.name.endswith(".summary.md")]
        if not args.all:
            targets = [p for p in targets if not p.with_suffix(".summary.md").exists()]
        if not targets:
            print(f"nothing to summarize in {target}")
            return

    for t in targets:
        print(f"summarizing {t} ...")
        out = summarize_file(t)
        print(f"  wrote {out}")


def cmd_install_skills(args: argparse.Namespace) -> None:
    for dest in install_skills(args.dest):
        print(f"installed: {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="minne")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Show session files and record-type counts for cwd")
    p_scan.add_argument("--cwd", type=Path, default=None)
    p_scan.set_defaults(func=cmd_scan)

    p_ing = sub.add_parser("ingest", help="Ingest sessions into <inbox>/<repo>/")
    p_ing.add_argument("--cwd", type=Path, default=None,
                       help="only ingest sessions from this cwd (default: all projects)")
    p_ing.add_argument("--inbox", type=Path, default=default_inbox(),
                       help=f"inbox root (default: $MINNE_HOME/inbox or ~/minne/inbox)")
    p_ing.set_defaults(func=cmd_ingest)

    p_sum = sub.add_parser("summarize", help="Summarize transcripts via `claude -p` Haiku")
    p_sum.add_argument("path", type=Path, nargs="?", default=default_inbox(),
                       help="transcript file, or directory tree (default: inbox)")
    p_sum.add_argument("--all", action="store_true",
                       help="re-summarize even if .summary.md already exists")
    p_sum.set_defaults(func=cmd_summarize)

    p_inst = sub.add_parser("install-skills", help="Install Claude Code skill into ~/.claude/skills/")
    p_inst.add_argument("--dest", type=Path, default=None,
                        help="override skills root (default: ~/.claude/skills)")
    p_inst.set_defaults(func=cmd_install_skills)

    args = parser.parse_args()
    args.func(args)
