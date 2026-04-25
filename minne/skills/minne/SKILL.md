---
name: minne
description: Capture the current Claude Code conversation into ./inbox/ as markdown, then produce a short Haiku-generated summary of outcomes and decisions. Use when the user says "capture this", "save the conversation", "remember what we did", "minne it", or invokes /minne. Also use proactively at the natural end of a non-trivial work session before context is lost.
---

# minne — capture conversation + summarize

Two-step recipe: ingest the live JSONL of the current session into markdown, then ask Haiku for a concise outcome summary.

## When to use

- User asks to capture / save / remember the conversation.
- User invokes `/minne`.
- Proactively at the end of a substantial work session (multiple commits, a feature shipped, a bug rooted out) — offer it in one line, don't auto-run.

Skip for trivial Q&A turns.

## Step 1 — ingest

Run from the project's working directory (the cwd where Claude Code is running):

```bash
minne ingest
```

This writes one markdown file per session into `./inbox/<session-id>.md`. The current live session is the file with the most recent mtime.

If `minne` isn't on PATH, run it via uv from the minne checkout:

```bash
uv run --project ~/r/minne minne ingest --cwd "$PWD" --inbox ./inbox
```

## Step 2 — summarize

```bash
minne summarize
```

Picks the newest transcript in `./inbox/` and shells out to `claude -p` with Haiku to produce `inbox/<session-id>.summary.md`. Uses the Claude Code subscription (no API spend). Report the summary path back to the user; don't paste the full summary unless asked.

## Output convention

- Full transcript: `inbox/<session-id>.md` (front matter: session_id, started, ended, cwd)
- Summary:        `inbox/<session-id>.summary.md`

Both live in `./inbox/`, which is gitignored by default in minne-managed projects. If the host project doesn't ignore `inbox/`, mention it once so the user can decide.
