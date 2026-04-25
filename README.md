# minne

Agent memory system for Claude Code.

`minne` captures Claude Code conversation history (and arbitrary clips) into a per-repo `inbox/`, then runs a second `digest` pass that shells out to Haiku to produce keyword-dense summaries and promote items into a searchable `store/`.

## Install

```bash
uv tool install minne
# or
pipx install minne
```

Optional dependency: the `claude` CLI on PATH (only used by `minne digest`). Digestion runs through the Claude Code subscription, not the API.

## Use

```bash
minne ingest          # ingest every Claude Code session into ~/minne/inbox/chats/<repo>/
minne add FILE | -    # add a clip from a file or stdin
minne digest          # process inbox items into ~/minne/store/<type>/<repo>/
minne install-skills  # install the bundled "minne" Claude Code skill into ~/.claude/skills/
```

`minne` is a global tool: by default it walks every project under `~/.claude/projects/` and groups transcripts by repo, resolved via `git rev-parse --show-toplevel` of the session's cwd (falling back to the cwd basename, or `_unknown/` if the path is gone). Override roots with `--inbox PATH` / `--store PATH` or `MINNE_HOME` (defaults: `~/minne/inbox`, `~/minne/store`).

`--cwd PATH` restricts `ingest` to a single project. `digest --since 1d` limits to recent items.

After `install-skills`, the agent itself can invoke `minne ingest && minne digest` at the end of a non-trivial work session.

## What gets kept

The ingest pass keeps `text` blocks from `user` and `assistant` messages. It drops tool calls, tool results, thinking blocks, and system-injected (`isMeta`) records like skill expansions. Each transcript opens with YAML front matter:

```yaml
---
session_id: 7890dec8-ff9b-46e8-8ed3-fcae0eb8da55
started: 2026-04-25T07:58:18.036Z
ended: 2026-04-25T09:24:00.952Z
cwd: /home/v/r/minne
---
```

If `cwd` changes mid-session (you `cd`'d), `cwds:` lists them all and an inline `> cwd changed to ...` marker shows where in the conversation the move happened.

## What summaries look like

Summaries are written by Haiku and meant to be searched, not read. They describe what the conversation is *about* — topics, file paths, libraries, commands, jargon — not what was decided or built. The idea is that grep through `~/minne/store/chats/**/summary.md` surfaces the right transcript, then you read the full thing.

## Layout

```
~/minne/
├── inbox/
│   ├── chats/<repo>/<session-id>.md             # raw chat, awaiting digest
│   └── clips/<repo>/<hint>-<short-uuid>.json    # `minne add` payload + metadata
└── store/
    └── chats/<repo>/<date>-<slug>/
        ├── chat.md              # final transcript
        └── summary.md           # keyword index
```

`minne ingest` writes new sessions into `inbox/chats/`. `minne digest` runs Haiku for each undigested transcript, wraps it into `store/chats/<repo>/<date>-<slug>/`, and moves the chat there. The slug comes from Haiku via `slug:` in summary front matter; the date comes from the transcript's `started:`. Re-running `minne ingest` looks up existing transcripts by `session_id:` in their front matter (across both inbox and store) and updates them in place.

## Requirements

- Python ≥ 3.11
- Claude Code (only for `minne digest`)
