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

The store is plain markdown under `~/minne/store/`. Two kinds of memory live there:

- **Clips** — explicit memos the user (or you) chose to save via `minne add`. Live at `store/clips/<repo>/<name>.md` or, when correlated with a chat, at `store/chats/<repo>/<date>-<slug>/clips/<name>.md` with a `chat:` link back to the conversation.
- **Chats** — full digested conversations at `store/chats/<repo>/<date>-<slug>/{chat.md,summary.md}`. Big, noisy, full of incidental detail.

**Search clips first.** They are deliberate, hand-curated signal — a hit there is almost always more relevant than a hit in chat transcripts. Only fall back to chats if clips don't answer the question.

```bash
rg -il "KEYWORDS" ~/minne/store/ -g '**/clips/**' -g '!chats/**/chat.md'  # clips only
rg -il "KEYWORDS" ~/minne/store/                                          # everything
rg -i  "KEYWORDS" ~/minne/store/chats/<repo>/                             # scope to one project
fd . ~/minne/store/ -e md | head                                          # browse
```

Workflow:

1. Pick 2–3 distinct keywords from the user's question (names, errors, commands — not generic words).
2. Search **clips first** with `rg -il`. If a clip looks relevant, `Read` it; follow the `chat:` link only if you need surrounding context.
3. If clips don't cover it, widen to all of `~/minne/store/` (chats included).
4. If still nothing, broaden terms before giving up.
5. Cite the file path back to the user when you use a memory, so they can verify.

Treat memories as point-in-time notes: a fact recorded six months ago may be stale. If a memory conflicts with what you observe in the live repo, trust the live repo and tell the user the memory looks out of date.

## Store paths (for reference)

- `~/minne/store/clips/<repo>/<name>.md` — clip not tied to any chat
- `~/minne/store/chats/<repo>/<date>-<slug>/clips/<name>.md` — clip linked to its chat (frontmatter has `chat: ../chat.md`)
- `~/minne/store/chats/<repo>/<date>-<slug>/{chat.md, summary.md}` — digested chat
- Override the root with `--store` or `MINNE_HOME`
