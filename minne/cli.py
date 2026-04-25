import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from minne.clip import add_clip
from minne.install import install_skills
from minne.reader import iter_records, iter_session_files, project_dir_for_cwd, projects_root
from minne.render import render_session
from minne.repo import resolve_repo
from minne.summarize import summarize_file


def default_root() -> Path:
    return Path(os.environ.get("MINNE_HOME", str(Path.home() / "minne")))


def default_inbox() -> Path:
    return default_root() / "inbox"


def default_store() -> Path:
    return default_root() / "store"


def _is_transcript(p: Path) -> bool:
    return p.suffix == ".md" and not p.name.endswith(".summary.md") and p.name != "summary.md"


def _parse_since(s: str) -> datetime:
    m = re.fullmatch(r"(\d+)d", s)
    if m:
        return datetime.now(timezone.utc) - timedelta(days=int(m.group(1)))
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"--since must be 'Nd' (days) or YYYY-MM-DD, got {s!r}"
        ) from e


def _started_of(transcript: Path) -> datetime | None:
    try:
        head = transcript.read_text(encoding="utf-8", errors="replace")[:512]
    except OSError:
        return None
    m = re.search(r"^started:\s*(\S+)", head, re.MULTILINE)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
    except ValueError:
        return None


def _summary_for(transcript: Path) -> Path:
    if transcript.name == "chat.md":
        return transcript.with_name("summary.md")
    return transcript.with_name(f"{transcript.stem}.summary.md")


def _repo_of(transcript: Path) -> str:
    """Repo dir name from a transcript path. inbox/<repo>/<id>.md -> repo;
    store/chats/<repo>/<date>-<slug>/chat.md -> repo."""
    if transcript.name == "chat.md":
        return transcript.parent.parent.name
    return transcript.parent.name


def _scan_session_ids(*roots: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*.md"):
            if not _is_transcript(p):
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
    store: Path = args.store
    inbox.mkdir(parents=True, exist_ok=True)
    existing = _scan_session_ids(inbox, store)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() if args.days else None
    written = 0
    skipped = 0
    for pdir in _project_dirs(args):
        for f in iter_session_files(pdir):
            if cutoff is not None and f.stat().st_mtime < cutoff:
                continue
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
                repo_dir = inbox / "chats" / repo
                repo_dir.mkdir(parents=True, exist_ok=True)
                out = repo_dir / f"{session_id}.md"
            out.write_text(md, encoding="utf-8")
            print(f"  wrote {out}  ({len(md)} bytes)")
            written += 1
    print(f"done: {written} written, {skipped} empty")


def cmd_digest(args: argparse.Namespace) -> None:
    inbox: Path = args.inbox
    store: Path = args.store
    target: Path = args.path

    if target.is_file():
        targets = [target]
    else:
        roots = [target] if target != inbox else [inbox, store]
        chats: list[Path] = []
        for r in roots:
            if r.is_dir():
                chats.extend(p for p in r.rglob("*.md") if _is_transcript(p))
        chats.sort(key=lambda p: p.stat().st_mtime)
        if not args.all:
            chats = [p for p in chats if not _summary_for(p).exists()]
        if args.since:
            cutoff = _parse_since(args.since)
            chats = [p for p in chats if (s := _started_of(p)) and s >= cutoff]
        targets = chats
        if not targets:
            print("nothing to digest")
            return

    jobs = max(1, args.jobs)

    def _one(t: Path) -> tuple[Path, Path | None, BaseException | None]:
        target_dir = store / "chats" / _repo_of(t)
        try:
            return t, summarize_file(t, target_repo_dir=target_dir), None
        except BaseException as e:
            return t, None, e

    if jobs == 1:
        for t in targets:
            print(f"digesting {t} ...", flush=True)
            _, out, err = _one(t)
            if err is not None:
                print(f"  failed: {err}", file=sys.stderr, flush=True)
            else:
                print(f"  wrote {out}", flush=True)
        return

    print(f"digesting {len(targets)} transcripts with {jobs} workers ...", flush=True)
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futures = [ex.submit(_one, t) for t in targets]
        for fut in as_completed(futures):
            t, out, err = fut.result()
            if err is not None:
                print(f"  failed {t}: {err}", file=sys.stderr, flush=True)
            else:
                print(f"  wrote {out}", flush=True)


def cmd_add(args: argparse.Namespace) -> None:
    if args.file is None or str(args.file) == "-":
        text = sys.stdin.read()
        source = "stdin"
    else:
        text = args.file.read_text(encoding="utf-8")
        source = str(args.file.resolve())
    if not text.strip():
        print("nothing to add (empty input)", file=sys.stderr)
        sys.exit(2)
    out = add_clip(text, source, args.cwd or Path.cwd(), args.inbox)
    print(f"added {out}")


def cmd_install_skills(args: argparse.Namespace) -> None:
    for dest in install_skills(args.dest):
        print(f"installed: {dest}")


def _add_root_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--inbox", type=Path, default=default_inbox(),
                   help="landing zone for fresh ingests (default: $MINNE_HOME/inbox)")
    p.add_argument("--store", type=Path, default=default_store(),
                   help="store for summarized sessions (default: $MINNE_HOME/store)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="minne")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Ingest sessions into inbox/<repo>/")
    p_ing.add_argument("--cwd", type=Path, default=None,
                       help="only ingest sessions from this cwd (default: all projects)")
    p_ing.add_argument("--days", type=int, default=None,
                       help="only ingest sessions modified in the last N days")
    _add_root_args(p_ing)
    p_ing.set_defaults(func=cmd_ingest)

    p_dig = sub.add_parser("digest", help="Process inbox items into store/ (chats: summarize via Haiku and move)")
    p_dig.add_argument("path", type=Path, nargs="?", default=default_inbox(),
                       help="file or directory to digest (default: inbox; sweeps inbox+store)")
    p_dig.add_argument("--all", action="store_true",
                       help="re-digest even if a digested artifact already exists")
    p_dig.add_argument("--since", default=None,
                       help="only items started since this point: 'Nd' or YYYY-MM-DD")
    p_dig.add_argument("--jobs", "-j", type=int, default=4,
                       help="number of parallel digest workers (default: 4)")
    _add_root_args(p_dig)
    p_dig.set_defaults(func=cmd_digest)

    p_add = sub.add_parser("add", help="Add a text clip to inbox/clips/<repo>/<uuid>.json")
    p_add.add_argument("file", type=Path, nargs="?", default=None,
                       help="file to add; '-' or omitted reads from stdin")
    p_add.add_argument("--cwd", type=Path, default=None,
                       help="treat as if run from this dir (for repo/branch resolution)")
    _add_root_args(p_add)
    p_add.set_defaults(func=cmd_add)

    p_inst = sub.add_parser("install-skills", help="Install Claude Code skill into ~/.claude/skills/")
    p_inst.add_argument("--dest", type=Path, default=None,
                        help="override skills root (default: ~/.claude/skills)")
    p_inst.set_defaults(func=cmd_install_skills)

    args = parser.parse_args()
    args.func(args)
