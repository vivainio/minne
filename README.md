# minne

Agent memory system for Claude Code.

`minne` reads Claude Code conversation history from `~/.claude/projects/<encoded-cwd>/*.jsonl` for the working directory you're in, and writes per-session markdown into a local `inbox/`. A second pass shells out to `claude -p` with Haiku to produce a short, keyword-dense summary of each transcript that's good for `grep`-ing months later.

## Install

```bash
uv tool install minne
# or
pipx install minne
```

Optional dependency: the `claude` CLI on PATH (only used by `minne summarize`). Summarization runs through the Claude Code subscription, not the API.

## Use

```bash
minne ingest          # writes inbox/<session-id>.md per session for cwd
minne summarize       # writes inbox/<session-id>.summary.md for any transcript missing one
minne scan            # show record-type counts per session for cwd
minne install-skills  # install the bundled "minne" Claude Code skill into ~/.claude/skills/
```

After `install-skills`, the agent itself can invoke `minne ingest && minne summarize` at the end of a non-trivial work session.

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

Summaries are written by Haiku and meant to be searched, not read. They describe what the conversation is *about* — topics, file paths, libraries, commands, jargon — not what was decided or built. The idea is that grep through `inbox/*.summary.md` surfaces the right transcript, then you read the full thing.

## Layout

```
./inbox/
├── 7890dec8-….md          # full transcript
└── 7890dec8-….summary.md  # keyword index
```

`./inbox/` is gitignored by default (in this repo).

## Requirements

- Python ≥ 3.11
- Claude Code (only for `minne summarize`)
