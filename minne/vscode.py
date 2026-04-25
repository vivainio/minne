"""Reader for VS Code Copilot Chat sessions.

VS Code persists Copilot Chat history per workspace under
``<workspaceStorage>/<storage-id>/chatSessions/<sid>.jsonl`` with a
two-record format: ``kind:0`` carries the initial requests array,
``kind:2`` patches append nested values (e.g. response chunks).

The companion ``workspace.json`` exposes the workspace folder as a URI:
``file:///...`` for native paths, ``vscode-remote://wsl+<distro>/...``
for WSL workspaces. We decode both shapes back to a Linux/Windows path
so ``resolve_repo`` can bucket the session correctly.

This logic mirrors what the upstream ``chat-transcript`` skill does."""

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote


def _candidate_storage_roots() -> list[Path]:
    """Known places VS Code keeps workspaceStorage. We probe each and
    silently skip the missing ones, so this works on Linux, macOS, and
    WSL (which sees its host's Roaming dir under /mnt/c)."""
    roots: list[Path] = []
    home = Path.home()

    # Native Linux / macOS-Linux build
    roots.append(home / ".config" / "Code" / "User" / "workspaceStorage")
    roots.append(home / ".config" / "Code - Insiders" / "User" / "workspaceStorage")

    # macOS
    roots.append(home / "Library" / "Application Support" / "Code" / "User" / "workspaceStorage")
    roots.append(
        home / "Library" / "Application Support" / "Code - Insiders" / "User" / "workspaceStorage"
    )

    # Windows (native)
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "Code" / "User" / "workspaceStorage")
        roots.append(Path(appdata) / "Code - Insiders" / "User" / "workspaceStorage")

    # WSL: probe the Windows host's Roaming for each user under /mnt/c/Users/.
    if sys.platform.startswith("linux"):
        users = Path("/mnt/c/Users")
        if users.is_dir():
            for u in users.iterdir():
                if not u.is_dir() or u.name in {"All Users", "Default", "Default User", "Public"}:
                    continue
                base = u / "AppData" / "Roaming"
                roots.append(base / "Code" / "User" / "workspaceStorage")
                roots.append(base / "Code - Insiders" / "User" / "workspaceStorage")

    return [r for r in roots if r.is_dir()]


def _is_wsl() -> bool:
    return sys.platform.startswith("linux") and Path("/mnt/c").is_dir()


def _windows_to_wsl(path: str) -> str:
    """`c:/r/foo` -> `/mnt/c/r/foo` so a WSL-side `git rev-parse` can find it."""
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        rest = path[2:].lstrip("/\\").replace("\\", "/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    return path


def _decode_folder_uri(uri: str) -> str | None:
    """Convert a workspace.json folder URI to a local path.

    Handles:
      file:///home/v/r/foo            -> /home/v/r/foo
      file:///c%3A/r/foo              -> c:/r/foo  (or /mnt/c/r/foo on WSL)
      vscode-remote://wsl%2Bubuntu/.. -> /...      (the Linux path, native on WSL)
    """
    if not uri:
        return None

    if uri.startswith("vscode-remote://"):
        rest = uri[len("vscode-remote://") :]
        slash = rest.find("/")
        if slash < 0:
            return None
        # Strip "<authority>/" (e.g. "wsl+ubuntu-24.04/") and keep the path.
        return unquote(rest[slash:])

    for prefix in ("file:///", "file://"):
        if uri.startswith(prefix):
            path = unquote(uri[len(prefix) :])
            # `c:/r/foo` from VS Code on Windows: leave as-is on Windows,
            # rewrite to /mnt/c/... when we're on WSL so git calls work.
            if len(path) >= 2 and path[1] == ":":
                return _windows_to_wsl(path) if _is_wsl() else path
            if not path.startswith("/"):
                path = "/" + path
            return path

    return None


def iter_session_jsonls(roots: list[Path] | None = None) -> Iterator[tuple[Path, Path]]:
    """Yield (storage_dir, session_jsonl) for every Copilot Chat session
    on the system. Resilient to missing workspace.json or chatSessions/."""
    for root in roots or _candidate_storage_roots():
        for storage_dir in root.iterdir():
            chat_dir = storage_dir / "chatSessions"
            if not chat_dir.is_dir():
                continue
            for jl in chat_dir.glob("*.jsonl"):
                yield storage_dir, jl


def session_cwd(storage_dir: Path) -> str | None:
    ws = storage_dir / "workspace.json"
    if not ws.is_file():
        return None
    try:
        data = json.loads(ws.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    folder = data.get("folder")
    return _decode_folder_uri(folder) if isinstance(folder, str) else None


def session_mtime(session_jsonl: Path) -> float:
    try:
        return session_jsonl.stat().st_mtime
    except OSError:
        return 0.0


def _load_messages(session_jsonl: Path) -> tuple[list[dict], int, int]:
    """Reconstruct the request list from kind:0 + kind:2 patches and emit
    a list of {role, content, ts_ms} entries plus (first_ts, last_ts)."""
    requests_state: dict[int, dict] = {}

    with session_jsonl.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = entry.get("kind")
            if kind == 0:
                for idx, req in enumerate(entry.get("v", {}).get("requests", [])):
                    requests_state[idx] = req
            elif kind == 2:
                k = entry.get("k", [])
                v = entry.get("v", [])
                if (
                    len(k) == 3
                    and k[0] == "requests"
                    and isinstance(k[1], int)
                    and isinstance(v, list)
                ):
                    idx = k[1]
                    if idx in requests_state:
                        requests_state[idx][k[2]] = requests_state[idx].get(k[2], []) + v

    messages: list[dict] = []
    first_ts = 0
    last_ts = 0
    for idx in sorted(requests_state):
        req = requests_state[idx]
        ts = int(req.get("timestamp") or 0)
        if ts and not first_ts:
            first_ts = ts
        if ts:
            last_ts = ts

        user_text = (req.get("message") or {}).get("text", "").strip()
        if user_text:
            messages.append({"role": "user", "content": user_text, "ts": ts})

        text_parts: list[str] = []
        for part in req.get("response") or []:
            if not isinstance(part, dict):
                continue
            if part.get("kind") in {"mcpServersStarting", "thinking", "toolInvocationSerialized"}:
                continue
            value = part.get("value", "")
            if value and isinstance(value, str):
                text_parts.append(value)
        assistant_text = "".join(text_parts).strip()
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text, "ts": ts})

    return messages, first_ts, last_ts


def _ms_to_iso(ms: int) -> str:
    if not ms:
        return ""
    from datetime import UTC, datetime

    return (
        datetime.fromtimestamp(ms / 1000, tz=UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def render_session(session_jsonl: Path, storage_dir: Path | None = None) -> str:
    """Return a markdown transcript for a VS Code Copilot Chat session,
    or '' if there are no user/assistant messages."""
    sid = session_jsonl.stem
    storage = storage_dir if storage_dir is not None else session_jsonl.parent.parent
    cwd = session_cwd(storage) or ""

    messages, first_ts, last_ts = _load_messages(session_jsonl)
    if not messages:
        return ""

    parts: list[str] = []
    for m in messages:
        parts.append(f"## {m['role']}\n\n{m['content']}")

    fm = ["---", f"session_id: {sid}", "producer: vscode-copilot-chat"]
    started = _ms_to_iso(first_ts)
    ended = _ms_to_iso(last_ts)
    if started:
        fm.append(f"started: {started}")
    if ended and ended != started:
        fm.append(f"ended: {ended}")
    if cwd:
        fm.append(f"cwd: {cwd}")
    fm.append("---")
    return "\n".join(fm) + "\n\n" + "\n\n".join(parts) + "\n"
