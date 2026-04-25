"""Load `~/.config/minne/config.toml` (XDG-aware).

Precedence for any setting: CLI flag > env var > config file > built-in default.
The loader is cached so repeated lookups are cheap; tests can call
``load_config.cache_clear()``.
"""

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "minne" / "config.toml"


TEMPLATE = """\
# minne config — all keys optional, defaults shown. Uncomment to override.

# Work-dir root. Env var MINNE_HOME wins over this.
# home = "~/minne"

# Independent overrides; default to <home>/inbox and <home>/store.
# inbox = "~/minne/inbox"
# store = "~/minne/store"

[digest]
# backend = "claude"   # "claude" | "copilot"
# model = "haiku"      # backend-specific (e.g. "gpt-4.1" for copilot)

# --- Using GitHub Copilot CLI instead of Claude --------------------
# For users without a Claude subscription. Requires `copilot` CLI on
# PATH and `gh auth login`. Pick a 0x-multiplier ("included") model so
# bulk digesting doesn't burn the premium-request quota — check the
# current list at https://docs.github.com/copilot/about-billing.
#
# [digest]
# backend = "copilot"
# model = "gpt-4.1"
"""


def _ensure_config(p: Path) -> None:
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(TEMPLATE, encoding="utf-8")


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    p = config_path()
    _ensure_config(p)
    with p.open("rb") as f:
        return tomllib.load(f)


def _expand(s: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(s)))


def home_from_config() -> Path | None:
    v = load_config().get("home")
    return _expand(v) if isinstance(v, str) else None


def inbox_from_config() -> Path | None:
    v = load_config().get("inbox")
    return _expand(v) if isinstance(v, str) else None


def store_from_config() -> Path | None:
    v = load_config().get("store")
    return _expand(v) if isinstance(v, str) else None


def digest_backend() -> str | None:
    v = load_config().get("digest", {}).get("backend")
    return v if isinstance(v, str) else None


def digest_model() -> str | None:
    v = load_config().get("digest", {}).get("model")
    return v if isinstance(v, str) else None
