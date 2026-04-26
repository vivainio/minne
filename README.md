# minne

Personal long-term memory for AI coding sessions.

`minne` captures Claude Code, GitHub Copilot CLI, and VS Code Copilot Chat conversations into a per-repo `inbox/`, then runs a digest pass that shells out to Haiku to produce a keyword-dense summary, a one-line `tldr`, and a short first-person `journal.md` entry. Digested items live in a searchable `store/` you can grep, list, and read back later. You can also save free-form notes (`minne add`) that get correlated to the conversation they came from.

## Install

```bash
uv tool install minne
```

Optional: the `claude` CLI on `PATH` (only used by `minne digest`). Digestion runs through the Claude Code subscription, not the API.

No Claude subscription? `minne digest` can shell out to GitHub Copilot CLI instead. Set `backend = "copilot"` under `[digest]` in `~/.config/minne/config.toml` (auto-created on first run) and pick a model. Copilot CLI must be on `PATH` and authenticated with `gh auth login`. Use a 0× / "included" model — e.g. `model = "gpt-4.1"` — so bulk digesting doesn't burn your premium-request quota; check the current included-model list in GitHub's Copilot billing docs, since the multipliers shift over time.

## Commands

```bash
minne ingest                # ingest sessions from Claude Code + Copilot CLI + VS Code Copilot Chat into ~/minne/inbox/
minne digest                # summarize inbox transcripts into ~/minne/store/ (4 workers by default)
minne add FILE | -          # save a free-form clip from a file or stdin
minne ls [--days N]         # list chats and clips in the current repo (or all repos outside one)
minne journal [--days N]    # print collected first-person diary entries, newest date first
minne install-skills        # install the bundled "minne" Claude Code skill into ~/.claude/skills/
```

`minne` is a global tool: ingest walks every project under `~/.claude/projects/`, every Copilot CLI session under `~/.copilot/session-state/`, and every VS Code Copilot Chat session under VS Code's `workspaceStorage/<id>/chatSessions/` (probed across Linux, macOS, Windows, and WSL ⇄ Windows host paths), grouping transcripts by repo via `git rev-parse --show-toplevel` of each session's cwd. Anything outside a git work tree lands in a `_nogit` bucket and gets classified into a topical category at digest time (see below). Override roots with `--inbox PATH` / `--store PATH` or `MINNE_HOME` (defaults: `~/minne/inbox`, `~/minne/store`).

`--cwd PATH` restricts ingest to a single Claude Code project. `--days N` limits ingest/ls/journal to the last N days. `--since 1d` works on `digest`.

## What ingest keeps

For Claude Code, the renderer keeps `text` blocks from `user` and `assistant` messages and drops tool calls, tool results, thinking blocks, and system-injected (`isMeta`) records. Edited file paths are extracted from `Edit`/`Write`/`MultiEdit`/`NotebookEdit` tool uses and listed in front matter (paths outside the session's cwd are dropped, so `/tmp` scratch files don't pollute the index).

For Copilot CLI, the renderer reads `events.jsonl` and keeps `user.message` / `assistant.message` events.

For VS Code Copilot Chat, the renderer reads each `chatSessions/<sid>.jsonl` and keeps the user prompt and assistant response text from each turn.

Both producers emit the same markdown shape:

```yaml
---
session_id: 7890dec8-ff9b-46e8-8ed3-fcae0eb8da55
producer: copilot-cli           # only set for Copilot sessions
started: 2026-04-25T07:58:18.036Z
ended:   2026-04-25T09:24:00.952Z
cwd: /home/v/r/minne
files_edited:
  - /home/v/r/minne/minne/cli.py
---
```

`minne`'s own digest sessions (the `claude -p` shell-out it launches itself) are detected by the prompt signature in their first user message and skipped, so the summarizer doesn't recursively index its own output.

## What digest produces

For each transcript, `minne digest` writes three sibling files into `store/chats/<repo>/<date>-<slug>/`:

- **`chat.md`** — the rendered transcript (moved out of inbox).
- **`summary.md`** — keyword-only topic index for grep, with `slug:` and `tldr:` in front matter.
- **`journal.md`** — 2–3 sentence first-person diary paragraph: the goal, the upshot, one notable insight. No code identifiers — those go in the summary's keyword list. `minne journal` concatenates these across repos by date.

`tldr` shows up under each chat in `minne ls`; `journal.md` is what `minne journal` prints.

Digest runs **4 workers in parallel by default** (each worker is a self-contained `claude -p` Haiku call). Tune with `-j N`. Per-transcript failures are reported and don't abort the batch.

## Clips

`minne add` saves an arbitrary text snippet — a paste, a command's stdout, a hand-written note — alongside the conversation that produced it:

```bash
echo "TEXT" | minne add -
some-cmd | minne add -
minne add path/to/file.md
```

A clip is captured with metadata (cwd, repo, branch, current Claude Code session id) into `inbox/clips/<repo>/<hint>-<short-uuid>.json`. At digest time:

- If the clip's `session_id` matches a digested chat in the same repo, the clip is rendered as markdown into that chat's directory at `store/chats/<repo>/<date>-<slug>/clips/<name>.md` and given a relative `chat:` link back to `chat.md`.
- Otherwise it lands at `store/clips/<repo>/<name>.md` (orphan).

The bundled Claude Code skill instructs the assistant to **search clips first** when answering a question — they're deliberate, hand-curated memos, so a hit there is worth more than a hit in the chat transcripts.

## `_nogit` and topical categories

Sessions that didn't happen inside a git work tree (random shell work, Copilot CLI in `/tmp`, notes in `~`) get bucketed under `_nogit` at ingest. At digest time, the summarizer is given the existing categories under `store/chats/nogit/` and asked to either reuse one or coin a new short kebab-case category. The chat then lands at:

```
store/chats/nogit/<category>/<date>-<slug>/{chat.md,summary.md,journal.md}
```

So a one-off rsync question and a one-off bash question both end up filed under stable categories like `command-line-tools/` or `shell-knowledge/` instead of inventing a new bucket per cwd.

## Layout

```
~/minne/
├── inbox/
│   ├── chats/<repo>/<session-id>.md                    # raw transcript awaiting digest
│   ├── chats/_nogit/<session-id>.md                    # non-git, awaiting categorization
│   └── clips/<repo>/<hint>-<short-uuid>.json           # `minne add` payload + metadata
└── store/
    ├── chats/
    │   ├── <repo>/<date>-<slug>/
    │   │   ├── chat.md                                 # rendered transcript
    │   │   ├── summary.md                              # keyword index (front matter: slug, tldr)
    │   │   ├── journal.md                              # first-person diary entry
    │   │   └── clips/<name>.md                         # clips correlated to this chat
    │   └── nogit/<category>/<date>-<slug>/{...}        # non-git chats, categorized
    └── clips/<repo>/<name>.md                          # orphan clips (no matching chat)
```

`minne ingest` looks up existing transcripts by `session_id:` (across inbox + store) and updates them in place, so re-ingesting is safe.

## The bundled skill

`minne install-skills` drops a Claude Code skill into `~/.claude/skills/minne/` that teaches the agent two things:

1. **When and how to add a memory.** Self-contained one-paragraph notes — the conclusion, the gotcha, the hard-won command — not whole conversations. Triggered by "remember this", "save to minne", "minne it", or proactively after a non-trivial finding.
2. **How to search the store.** Clips first (deliberate signal), chats second (noisy), with `rg` recipes for both. Always cite the file path so the user can verify.

## Requirements

- Python ≥ 3.11
- Claude Code (only for `minne digest`)
