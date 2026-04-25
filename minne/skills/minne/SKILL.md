---
name: minne
description: Capture the current Claude Code conversation into ~/minne/inbox/<repo>/ as markdown, then produce a short Haiku-generated keyword index. Use when the user says "capture this", "save the conversation", "remember what we did", "minne it", or invokes /minne. Also use proactively at the natural end of a non-trivial work session before context is lost.
---

# minne — capture conversation + summarize

Two commands: ingest live JSONL into markdown, then have Haiku build a keyword index for future search.

## When to use

- User asks to capture / save / remember the conversation.
- User invokes `/minne`.
- Proactively at the end of a substantial work session (multiple commits, a feature shipped, a bug rooted out) — offer it in one line, don't auto-run.

Skip for trivial Q&A turns.

## Run

```bash
minne ingest && minne summarize
```

`minne ingest` walks every Claude Code project (default) and writes one markdown file per session into `~/minne/inbox/<repo>/<session-id>.md`. To capture only the current session's project, pass `--cwd "$PWD"`.

`minne summarize` shells out to `claude -p --tools "" --model haiku` for every transcript that doesn't yet have a sibling `.summary.md`. Uses the Claude Code subscription (no API spend). After summarization, both transcript and summary are renamed to `<YYYY-MM-DD>-<slug>.{md,summary.md}`.

Report the new file paths back to the user; don't paste full summaries unless asked.

## Output

- Inbox root: `~/minne/inbox/<repo>/` (override with `--inbox` or `MINNE_HOME`)
- Transcript front matter: `session_id`, `started`, `ended`, `cwd`
- Summary front matter: `slug`, `started`
