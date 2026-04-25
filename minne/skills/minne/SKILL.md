---
name: minne
description: Capture the current Claude Code conversation (or a clip) into ~/minne/inbox/, then digest into ~/minne/store/ with a Haiku-generated keyword index. Use when the user says "capture this", "save the conversation", "remember what we did", "minne it", or invokes /minne. Also use proactively at the natural end of a non-trivial work session before context is lost.
---

# minne — capture + digest

Two commands: ingest the live session (or `add` a clip), then `digest` to summarize and promote into the store.

## When to use

- User asks to capture / save / remember the conversation.
- User invokes `/minne`.
- Proactively at the end of a substantial work session (multiple commits, a feature shipped, a bug rooted out) — offer it in one line, don't auto-run.
- `minne add -` to capture an arbitrary text snippet (paste, file, stdout) as a clip.

Skip for trivial Q&A turns.

## Run

```bash
minne ingest && minne digest
```

`minne ingest` walks every Claude Code project and writes a flat `~/minne/inbox/chats/<repo>/<session-id>.md` per session. Pass `--cwd "$PWD"` to limit to the current project.

`minne digest` shells out to `claude -p --tools "" --model haiku` for every undigested transcript. Uses the Claude Code subscription (no API spend). It moves the session out of `inbox/chats/` into `~/minne/store/chats/<repo>/<date>-<slug>/` containing `chat.md` and `summary.md`.

For ad-hoc material:

```bash
minne add path/to/file        # capture a file as a clip
some-cmd | minne add -        # capture stdout
```

Report the new directory paths back to the user; don't paste full summaries unless asked.

## Output

- Chats inbox: `~/minne/inbox/chats/<repo>/<session-id>.md`
- Clips inbox: `~/minne/inbox/clips/<repo>/<hint>-<short-uuid>.json`
- Digested chats: `~/minne/store/chats/<repo>/<date>-<slug>/{chat.md, summary.md}`
- Override roots with `--inbox PATH` / `--store PATH` or `MINNE_HOME`
- Transcript front matter: `session_id`, `started`, `ended`, `cwd`
- Summary front matter: `slug`, `started`
