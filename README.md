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
minne ingest          # ingest every Claude Code session into ~/minne/inbox/<repo>/
minne summarize       # produce sibling .summary.md for every transcript missing one
minne scan            # record-type counts for the cwd's project dir
minne install-skills  # install the bundled "minne" Claude Code skill into ~/.claude/skills/
```

`minne` is a global tool: by default it walks every project under `~/.claude/projects/` and groups transcripts into `~/minne/inbox/<repo>/` (resolving the project's cwd via `git rev-parse --show-toplevel`, falling back to the dir basename, or `_unknown/` if the path is gone). Override the inbox root with `--inbox PATH` or `MINNE_HOME`.

`--cwd PATH` restricts ingest to a single project dir.

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
~/minne/inbox/
├── minne/
│   ├── 2026-04-25-minne-conversation-indexing.md
│   └── 2026-04-25-minne-conversation-indexing.summary.md
├── nspect/
│   └── ...
└── _unknown/   # sessions whose original cwd no longer exists
```

After summarization, transcripts are renamed to `<YYYY-MM-DD>-<slug>.{md,summary.md}` (slug proposed by Haiku). Re-running `minne ingest` finds the renamed files via `session_id:` in their YAML front matter and updates them in place — no duplicates.

## Requirements

- Python ≥ 3.11
- Claude Code (only for `minne summarize`)
