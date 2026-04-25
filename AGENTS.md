# Agent Instructions

Guidelines for AI agents working on this codebase.

## Project

`minne` is an agent memory system. It reads Claude Code conversation history
from `~/.claude/projects/<encoded-cwd>/*.jsonl` and stores extracted material
in an `inbox/` folder, scoped per project (identified by the cwd at run time).

The JSONL format is an undocumented Claude Code internal — parse tolerantly.

## Code Quality

Use ruff for formatting and linting:
```bash
ruff format .
ruff check . --fix
```

## Package Management

Use uv, not pip:
```bash
uv add <package>
uv sync
uv run <command>
```

## Type Annotations

Required for all code. Use Python 3.11+ built-in generics (`list[str]`, not `List[str]`).
