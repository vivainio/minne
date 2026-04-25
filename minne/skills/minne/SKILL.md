---
name: minne
description: Add notes/clips to the user's personal memory store at ~/minne/ and search it. Use when the user says "remember this", "save to minne", "minne it", "what did we figure out about X", "search minne for Y", or invokes /minne. Also use proactively at the natural end of a non-trivial work session to offer saving a memory before context is lost.
---

# minne — add memories + search them

`minne` is the user's long-term, cross-session memory store at `~/minne/`. This skill covers two things only: **adding** a memory and **searching** existing ones. (Ingest/digest plumbing is internal — don't run it as part of this skill.)

## Add a memory

The right input is a focused, self-contained note: the conclusion, the gotcha, the decision, the snippet — not the whole conversation. Write it as if the user will read it cold in six months.

```bash
echo "TEXT" | minne add -          # capture text from stdin
minne add path/to/file             # capture an existing file
```

Use `--cwd "$PWD"` if you're not already in the repo the memory belongs to (it's used to bucket the clip under the right project).

When to add:

- User says "remember this", "save this to minne", "minne it", "capture this".
- Proactively after a non-trivial finding (root cause, gnarly fix, surprising config, hard-won command) — offer it in one line, don't auto-run.

What to write:

- One self-contained note per `add`. Title-style first line, then the substance.
- Include the *why* and any concrete commands / paths / IDs that future-you would need.
- Skip ephemeral state ("currently running", "today I…") — memories outlive the session.

Skip for trivial Q&A or anything already obvious from the code or git history.

## Search memories

The store is plain markdown under `~/minne/store/` (chats live in `store/chats/<repo>/<date>-<slug>/{chat.md,summary.md}`; clips live alongside). Search it with normal tools:

```bash
rg -i "KEYWORDS" ~/minne/store/                      # full-text
rg -il "KEYWORDS" ~/minne/store/                     # filenames only
rg -i "KEYWORDS" ~/minne/store/chats/<repo>/         # scope to one project
fd . ~/minne/store/ -e md | head                     # browse
```

Workflow:

1. Pick 2–3 distinct keywords from the user's question (names, errors, commands — not generic words).
2. `rg -il` first to find candidate files, then `Read` the promising ones.
3. If nothing hits, broaden terms or try `~/minne/inbox/` (undigested material).
4. Cite the file path back to the user when you use a memory, so they can verify.

Treat memories as point-in-time notes: a fact recorded six months ago may be stale. If a memory conflicts with what you observe in the live repo, trust the live repo and tell the user the memory looks out of date.

## Output paths (for reference)

- `~/minne/inbox/clips/<repo>/<hint>-<uuid>.json` — fresh clips
- `~/minne/inbox/chats/<repo>/<session-id>.md` — fresh chat captures
- `~/minne/store/chats/<repo>/<date>-<slug>/{chat.md, summary.md}` — digested
- Override with `--inbox` / `--store` or `MINNE_HOME`
