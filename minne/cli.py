import argparse
from collections import Counter
from pathlib import Path

from minne.reader import iter_records, iter_session_files, project_dir_for_cwd
from minne.render import render_session


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


def cmd_ingest(args: argparse.Namespace) -> None:
    pdir = project_dir_for_cwd(args.cwd)
    inbox: Path = args.inbox
    inbox.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for f in iter_session_files(pdir):
        md = render_session(iter_records(f))
        if not md:
            skipped += 1
            continue
        out = inbox / f"{f.stem}.md"
        out.write_text(md, encoding="utf-8")
        print(f"  wrote {out}  ({len(md)} bytes)")
        written += 1
    print(f"done: {written} written, {skipped} empty, into {inbox}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="minne")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Show session files and record-type counts for cwd")
    p_scan.add_argument("--cwd", type=Path, default=None)
    p_scan.set_defaults(func=cmd_scan)

    p_ing = sub.add_parser("ingest", help="Write per-session markdown into inbox/")
    p_ing.add_argument("--cwd", type=Path, default=None)
    p_ing.add_argument("--inbox", type=Path, default=Path("inbox"))
    p_ing.set_defaults(func=cmd_ingest)

    args = parser.parse_args()
    args.func(args)
