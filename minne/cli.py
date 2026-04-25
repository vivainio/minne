import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path

from minne import copilot, vscode
from minne.clip import add_clip, digest_clip
from minne.install import install_skills
from minne.reader import iter_records, iter_session_files, project_dir_for_cwd, projects_root
from minne.render import render_session
from minne.repo import NOGIT, resolve_repo
from minne.summarize import summarize_file


def default_root() -> Path:
    return Path(os.environ.get("MINNE_HOME", str(Path.home() / "minne")))


def default_inbox() -> Path:
    return default_root() / "inbox"


def default_store() -> Path:
    return default_root() / "store"


_NON_TRANSCRIPT_NAMES = {"summary.md", "journal.md"}


def _is_transcript(p: Path) -> bool:
    if p.suffix != ".md":
        return False
    if p.name in _NON_TRANSCRIPT_NAMES:
        return False
    if p.name.endswith(".summary.md") or p.name.endswith(".journal.md"):
        return False
    # Skip clip markdowns living under any "clips/" subdir (linked or orphan).
    return "clips" not in p.parts


def _parse_since(s: str) -> datetime:
    m = re.fullmatch(r"(\d+)d", s)
    if m:
        return datetime.now(UTC) - timedelta(days=int(m.group(1)))
    try:
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
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
    store/chats/<repo>/<date>-<slug>/chat.md -> repo;
    store/chats/nogit/<cat>/<date>-<slug>/chat.md -> _nogit (so re-digest
    routes back through the nogit classifier)."""
    if transcript.name == "chat.md":
        # nogit layout has one extra level: .../nogit/<cat>/<date>-<slug>/chat.md
        try:
            if transcript.parent.parent.parent.name == "nogit":
                return NOGIT
        except IndexError:
            pass
        return transcript.parent.parent.name
    return transcript.parent.name


_SUMMARIZER_MARKER = "You are indexing past Claude Code conversations"


def _is_summarizer_session(records: list[dict]) -> bool:
    """Detect transcripts produced by `minne digest` itself (the Haiku
    summarizer shell-out leaves its own session in ~/.claude/projects/).
    Match on the fixed PROMPT_HEAD signature in the first user message."""
    for r in records:
        if r.get("type") != "user":
            continue
        msg = r.get("message") or {}
        content = msg.get("content", r.get("content"))
        if isinstance(content, str):
            return _SUMMARIZER_MARKER in content
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    if _SUMMARIZER_MARKER in (c.get("text") or ""):
                        return True
            return False
        return False
    return False


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
    cutoff = (datetime.now(UTC) - timedelta(days=args.days)).timestamp() if args.days else None
    written = 0
    skipped = 0
    for pdir in _project_dirs(args):
        for f in iter_session_files(pdir):
            if cutoff is not None and f.stat().st_mtime < cutoff:
                continue
            session_id = f.stem
            records = list(iter_records(f))
            if _is_summarizer_session(records):
                skipped += 1
                continue
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

    if args.cwd is None:
        for sdir in copilot.iter_session_dirs():
            if cutoff is not None and copilot.session_mtime(sdir) < cutoff:
                continue
            session_id = sdir.name
            md = copilot.render_session(sdir)
            if not md:
                skipped += 1
                continue
            if session_id in existing:
                out = existing[session_id]
            else:
                repo = resolve_repo(copilot.session_cwd(sdir))
                repo_dir = inbox / "chats" / repo
                repo_dir.mkdir(parents=True, exist_ok=True)
                out = repo_dir / f"{session_id}.md"
            out.write_text(md, encoding="utf-8")
            print(f"  wrote {out}  ({len(md)} bytes)")
            written += 1

        for storage_dir, jl in vscode.iter_session_jsonls():
            if cutoff is not None and vscode.session_mtime(jl) < cutoff:
                continue
            session_id = jl.stem
            md = vscode.render_session(jl, storage_dir)
            if not md:
                skipped += 1
                continue
            if session_id in existing:
                out = existing[session_id]
            else:
                repo = resolve_repo(vscode.session_cwd(storage_dir))
                repo_dir = inbox / "chats" / repo
                repo_dir.mkdir(parents=True, exist_ok=True)
                out = repo_dir / f"{session_id}.md"
            out.write_text(md, encoding="utf-8")
            print(f"  wrote {out}  ({len(md)} bytes)")
            written += 1

    print(f"done: {written} written, {skipped} empty")


def _existing_nogit_categories(store: Path) -> list[str]:
    root = store / "chats" / "nogit"
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.glob("*") if d.is_dir())


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

    jobs = max(1, args.jobs)

    def _one(t: Path) -> tuple[Path, Path | None, BaseException | None]:
        repo = _repo_of(t)
        try:
            if repo == NOGIT:
                target_dir = store / "chats" / "nogit"
                cats = _existing_nogit_categories(store)
                return t, summarize_file(t, target_repo_dir=target_dir, nogit_categories=cats), None
            target_dir = store / "chats" / repo
            return t, summarize_file(t, target_repo_dir=target_dir), None
        except BaseException as e:
            return t, None, e

    if targets and jobs == 1:
        for t in targets:
            print(f"digesting {t} ...", flush=True)
            _, out, err = _one(t)
            if err is not None:
                print(f"  failed: {err}", file=sys.stderr, flush=True)
            else:
                print(f"  wrote {out}", flush=True)
    elif targets:
        print(f"digesting {len(targets)} transcripts with {jobs} workers ...", flush=True)
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futures = [ex.submit(_one, t) for t in targets]
            for fut in as_completed(futures):
                t, out, err = fut.result()
                if err is not None:
                    print(f"  failed {t}: {err}", file=sys.stderr, flush=True)
                else:
                    print(f"  wrote {out}", flush=True)

    _digest_clips(inbox, store)


def _digest_clips(inbox: Path, store: Path) -> None:
    clips_root = inbox / "clips"
    if not clips_root.is_dir():
        return
    by_repo: dict[str, list[Path]] = {}
    for p in clips_root.rglob("*.json"):
        by_repo.setdefault(p.parent.name, []).append(p)
    if not by_repo:
        return
    total = sum(len(v) for v in by_repo.values())
    print(f"digesting {total} clips ...", flush=True)
    from minne.clip import _index_chats_by_session

    for repo, paths in by_repo.items():
        index = _index_chats_by_session(store, repo)
        for p in paths:
            try:
                out = digest_clip(p, store, chat_index=index)
                print(f"  wrote {out}", flush=True)
            except BaseException as e:
                print(f"  failed {p}: {e}", file=sys.stderr, flush=True)


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


_TLDR_RE = re.compile(r"^tldr:\s*(.+?)\s*$", re.MULTILINE)


def _tldr_of(chat_dir: Path) -> str | None:
    summary = chat_dir / "summary.md"
    if not summary.is_file():
        return None
    try:
        head = summary.read_text(encoding="utf-8", errors="replace")[:1000]
    except OSError:
        return None
    if not head.startswith("---"):
        return None
    end = head.find("\n---", 3)
    if end < 0:
        return None
    m = _TLDR_RE.search(head[:end])
    return m.group(1).strip().strip("\"'") if m else None


def _in_git_repo(cwd: Path) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip() == "true"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _list_chat_dirs(label: str, chat_dirs: list[Path], orphan_clips: list[Path]) -> bool:
    if not chat_dirs and not orphan_clips:
        return False
    print(f"\n{label}/")
    for d in chat_dirs:
        clips = sorted((d / "clips").glob("*.md")) if (d / "clips").is_dir() else []
        tag = f"  [{len(clips)} clip{'s' if len(clips) != 1 else ''}]" if clips else ""
        print(f"  {d.name}{tag}")
        tldr = _tldr_of(d)
        if tldr:
            print(f"      {tldr}")
        for c in clips:
            print(f"    - {c.name}")
    if orphan_clips:
        print("  clips (no chat):")
        for c in orphan_clips:
            print(f"    - {c.name}")
    return True


def _list_one_repo(store: Path, repo: str, cutoff: str | None) -> bool:
    chat_root = store / "chats" / repo
    clip_root = store / "clips" / repo

    if repo == "nogit" and chat_root.is_dir():
        any_listed = False
        for cat_dir in sorted(d for d in chat_root.glob("*") if d.is_dir()):
            chat_dirs = sorted(
                (d for d in cat_dir.glob("*") if d.is_dir()),
                key=lambda d: d.name,
                reverse=True,
            )
            if cutoff:
                chat_dirs = [d for d in chat_dirs if d.name[:10] >= cutoff]
            if _list_chat_dirs(f"nogit/{cat_dir.name}", chat_dirs, []):
                any_listed = True
        orphan_clips = sorted(clip_root.glob("*.md")) if clip_root.is_dir() else []
        if orphan_clips:
            _list_chat_dirs("nogit (orphan clips)", [], orphan_clips)
            any_listed = True
        return any_listed

    chat_dirs = (
        sorted(
            (d for d in chat_root.glob("*") if d.is_dir()),
            key=lambda d: d.name,
            reverse=True,
        )
        if chat_root.is_dir()
        else []
    )
    if cutoff:
        chat_dirs = [d for d in chat_dirs if d.name[:10] >= cutoff]
    orphan_clips = sorted(clip_root.glob("*.md")) if clip_root.is_dir() else []
    return _list_chat_dirs(repo, chat_dirs, orphan_clips)


def cmd_ls(args: argparse.Namespace) -> None:
    store: Path = args.store
    cwd = args.cwd or Path.cwd()
    cutoff: str | None = None
    if args.days:
        cutoff = (datetime.now(UTC) - timedelta(days=args.days)).date().isoformat()

    if args.repo:
        repos = [args.repo]
        scope = f"repo: {args.repo}"
    elif _in_git_repo(cwd):
        repos = [resolve_repo(str(cwd))]
        scope = f"repo: {repos[0]} (cwd is in a git work tree)"
    else:
        chats_root = store / "chats"
        repos = (
            sorted(d.name for d in chats_root.glob("*") if d.is_dir())
            if chats_root.is_dir()
            else []
        )
        scope = f"all repos ({len(repos)})"

    print(scope)
    print(f"store: {store}")
    if cutoff:
        print(f"since: {cutoff}")

    any_listed = False
    for repo in repos:
        if _list_one_repo(store, repo, cutoff):
            any_listed = True
    if not any_listed:
        print("\n(nothing to show)")


def cmd_journal(args: argparse.Namespace) -> None:
    store: Path = args.store
    chats_root = store / "chats"
    if not chats_root.is_dir():
        print("(no journal entries yet)")
        return

    cutoff: str | None = None
    if args.days:
        cutoff = (datetime.now(UTC) - timedelta(days=args.days)).date().isoformat()

    repos = [args.repo] if args.repo else sorted(d.name for d in chats_root.glob("*") if d.is_dir())

    # entries: list of (date, repo_label, slug, journal_text)
    entries: list[tuple[str, str, str, str]] = []
    for repo in repos:
        repo_root = chats_root / repo
        if not repo_root.is_dir():
            continue
        # nogit chats live one level deeper: nogit/<category>/<date>-<slug>/
        if repo == "nogit":
            chat_dirs = [
                (f"nogit/{cat.name}", d)
                for cat in repo_root.glob("*")
                if cat.is_dir()
                for d in cat.glob("*")
                if d.is_dir()
            ]
        else:
            chat_dirs = [(repo, d) for d in repo_root.glob("*") if d.is_dir()]
        for label, chat_dir in chat_dirs:
            name = chat_dir.name
            if len(name) < 11 or name[10] != "-":
                continue
            date = name[:10]
            slug = name[11:]
            if cutoff and date < cutoff:
                continue
            jfile = chat_dir / "journal.md"
            if not jfile.is_file():
                continue
            try:
                text = jfile.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text:
                entries.append((date, label, slug, text))

    if not entries:
        print("(no journal entries match)")
        return

    entries.sort(key=lambda e: (e[0], e[1], e[2]), reverse=True)

    current_date: str | None = None
    for date, repo, slug, text in entries:
        if date != current_date:
            if current_date is not None:
                print()
            print(f"## {date}\n")
            current_date = date
        print(f"### {repo} — {slug}\n")
        print(text)
        print()


def cmd_install_skills(args: argparse.Namespace) -> None:
    for dest in install_skills(args.dest):
        print(f"installed: {dest}")


def _add_root_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--inbox",
        type=Path,
        default=default_inbox(),
        help="landing zone for fresh ingests (default: $MINNE_HOME/inbox)",
    )
    p.add_argument(
        "--store",
        type=Path,
        default=default_store(),
        help="store for summarized sessions (default: $MINNE_HOME/store)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="minne")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Ingest sessions into inbox/<repo>/")
    p_ing.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="only ingest sessions from this cwd (default: all projects)",
    )
    p_ing.add_argument(
        "--days", type=int, default=None, help="only ingest sessions modified in the last N days"
    )
    _add_root_args(p_ing)
    p_ing.set_defaults(func=cmd_ingest)

    p_dig = sub.add_parser(
        "digest", help="Process inbox items into store/ (chats: summarize via Haiku and move)"
    )
    p_dig.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=default_inbox(),
        help="file or directory to digest (default: inbox; sweeps inbox+store)",
    )
    p_dig.add_argument(
        "--all", action="store_true", help="re-digest even if a digested artifact already exists"
    )
    p_dig.add_argument(
        "--since", default=None, help="only items started since this point: 'Nd' or YYYY-MM-DD"
    )
    p_dig.add_argument(
        "--jobs", "-j", type=int, default=4, help="number of parallel digest workers (default: 4)"
    )
    _add_root_args(p_dig)
    p_dig.set_defaults(func=cmd_digest)

    p_add = sub.add_parser("add", help="Add a text clip to inbox/clips/<repo>/<uuid>.json")
    p_add.add_argument(
        "file",
        type=Path,
        nargs="?",
        default=None,
        help="file to add; '-' or omitted reads from stdin",
    )
    p_add.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="treat as if run from this dir (for repo/branch resolution)",
    )
    _add_root_args(p_add)
    p_add.set_defaults(func=cmd_add)

    p_ls = sub.add_parser("ls", help="List store objects (chats and clips) for a repo")
    p_ls.add_argument(
        "--cwd", type=Path, default=None, help="treat as if run from this dir (for repo resolution)"
    )
    p_ls.add_argument(
        "--repo",
        default=None,
        help="repo name to list (default: resolve from cwd; all repos when cwd is not a git work tree)",
    )
    p_ls.add_argument("--days", type=int, default=None, help="only show chats from the last N days")
    _add_root_args(p_ls)
    p_ls.set_defaults(func=cmd_ls)

    p_jrnl = sub.add_parser("journal", help="Print collected journal.md entries grouped by date")
    p_jrnl.add_argument("--repo", default=None, help="limit to one repo (default: all repos)")
    p_jrnl.add_argument(
        "--days", type=int, default=None, help="only show entries from the last N days"
    )
    _add_root_args(p_jrnl)
    p_jrnl.set_defaults(func=cmd_journal)

    p_inst = sub.add_parser(
        "install-skills", help="Install Claude Code skill into ~/.claude/skills/"
    )
    p_inst.add_argument(
        "--dest", type=Path, default=None, help="override skills root (default: ~/.claude/skills)"
    )
    p_inst.set_defaults(func=cmd_install_skills)

    args = parser.parse_args()
    args.func(args)
