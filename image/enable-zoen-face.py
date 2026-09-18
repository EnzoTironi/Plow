#!/usr/bin/env python3
"""Keep Zoen's live Hermes config: zoen-face on, yolo, models, no mid-turn chatter."""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

PLUGIN = "zoen-face"
CHAT = "plow-chat-platform"
SEED = Path("/opt/hermes/plow-seed/config.yaml")
OVERLAY = Path("/opt/hermes/plow-seed/zoen-config.yaml")
REPO_OVERLAY = Path(__file__).resolve().parents[1] / "runtime/config.yaml"
LIVE = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes")) / "config.yaml"
MODELS = {
    "model": {
        "default": "openai/gpt-5.6-luna",
        "provider": "plow",
    },
    "providers": {
        "plow": {
            "models": {
                "anthropic/claude-sonnet-5": {},
                "anthropic/claude-opus-5": {},
                "openai/gpt-5.6-luna": {},
                "moonshotai/kimi-k3": {},
            }
        }
    },
    "auxiliary": {
        "vision": {
            "provider": "plow",
            "model": "anthropic/claude-sonnet-5",
        }
    },
}
YOLO = {
    "approvals": {
        "mode": "off",
        "cron_mode": "approve",
        "single_query_mode": "approve",
        "unattended_mode": "approve",
    },
    "security": {"tirith_enabled": False},
    "busy_input_mode": "steer",
    "busy_ack_enabled": False,
    "display": {
        "interim_assistant_messages": False,
        "memory_notifications": "off",
        "background_process_notifications": "off",
        "platforms": {
            "plow_chat": {
                "tool_progress": "off",
                "long_running_notifications": False,
                "interim_assistant_messages": False,
            }
        },
    },
}
MARKERS = (
    "    - plow-chat-platform\n",
    "  - plow-chat-platform\n",
    "- plow-chat-platform\n",
)


def _listed(text: str) -> bool:
    return f"- {PLUGIN}" in text or f"-{PLUGIN}" in text


def _merge(dst: dict, src: dict) -> bool:
    changed = False
    for key, value in src.items():
        if isinstance(value, dict):
            nested = dst.get(key)
            if not isinstance(nested, dict):
                nested = {}
                dst[key] = nested
            changed = _merge(nested, value) or changed
        elif dst.get(key) != value:
            dst[key] = value
            changed = True
    return changed


def load_overlay() -> dict:
    if yaml is not None:
        for path in (OVERLAY, REPO_OVERLAY):
            try:
                if not path.is_file():
                    continue
                data = yaml.safe_load(path.read_text())
            except (OSError, yaml.YAMLError):
                continue
            if isinstance(data, dict) and data:
                return data
    return MODELS


def apply_runtime(data: dict) -> bool:
    changed = _merge(data, YOLO)
    return _merge(data, load_overlay()) or changed


def enable_plugin(data: dict) -> bool:
    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        plugins = {}
        data["plugins"] = plugins
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        enabled = []
    if PLUGIN in enabled:
        plugins["enabled"] = enabled
        return False
    if CHAT in enabled:
        enabled.insert(enabled.index(CHAT) + 1, PLUGIN)
    else:
        enabled.append(PLUGIN)
    plugins["enabled"] = enabled
    return True


def ensure_text(path: Path) -> bool:
    raw = path.read_text()
    if _listed(raw):
        return False
    for old in MARKERS:
        if old not in raw:
            continue
        indent = old[: old.index("-")]
        path.write_text(raw.replace(old, old + f"{indent}- {PLUGIN}\n", 1))
        return True
    raise SystemExit(f"plugins list moved in {path}")


def _replace(path: Path, text: str) -> None:
    stat = path.stat()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.chmod(tmp, stat.st_mode)
    try:
        os.chown(tmp, stat.st_uid, stat.st_gid)
    except PermissionError:
        pass
    tmp.replace(path)


def ensure_yaml(path: Path) -> bool:
    if yaml is None:
        return ensure_text(path)
    raw = path.read_text()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        return ensure_text(path)
    changed = enable_plugin(data)
    changed = apply_runtime(data) or changed
    if not changed:
        return False
    _replace(path, yaml.safe_dump(data, sort_keys=False))
    return True


def ensure(path: Path, *, text_only: bool = False) -> bool:
    if not path.is_file():
        return False
    if text_only:
        return ensure_text(path)
    return ensure_yaml(path)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        for raw in args:
            ensure(Path(raw))
        return 0
    if SEED.is_file():
        if yaml is None:
            ensure(SEED, text_only=True)
        else:
            ensure(SEED)
    if LIVE.is_file():
        ensure(LIVE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
