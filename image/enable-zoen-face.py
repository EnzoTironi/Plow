#!/usr/bin/env python3
"""Keep Zoen's live Hermes config: zoen-face on, yolo, models, no mid-turn chatter."""
from __future__ import annotations

import os
import shutil
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
BUNDLED_SKILL = Path("/opt/hermes/skills/zoen")
BUNDLED_SCRIPTS = Path("/opt/hermes/skills/zoen/scripts")
MODELS = {
    "model": {
        "default": "openai/gpt-5.6-luna",
        "provider": "plow",
    },
    "fallback_model": {
        "provider": "plow",
        "model": "anthropic/claude-sonnet-5",
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


def _same_tree(src: Path, dest: Path) -> bool:
    if not dest.is_dir():
        return False
    src_rels = {path.relative_to(src) for path in src.rglob("*") if path.is_file()}
    dest_rels = {path.relative_to(dest) for path in dest.rglob("*") if path.is_file()}
    if src_rels != dest_rels:
        return False
    return all(
        (dest / rel).read_bytes() == (src / rel).read_bytes() for rel in src_rels
    )


def _install_skill(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    for path in dest.rglob("*"):
        if path.is_file():
            path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)


def _drop(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink()
    return True


def refresh_image_scripts(
    home: str | None = None,
    *,
    bundled: Path | None = None,
    face: Path | None = None,
) -> bool:
    """Wipe leftover Zoen files on this line's volume and install the image skill.

    Plow keeps HERMES_HOME across revoke/redeploy. That leftover is the old hello.
    """
    del face
    env_home = (os.environ.get("HERMES_HOME") or "").strip()
    root = Path(home or env_home or "/var/lib/hermes")
    src = bundled if bundled is not None else (
        BUNDLED_SKILL if BUNDLED_SKILL.is_dir() else BUNDLED_SCRIPTS
    )
    dirty = False
    for path in (
        root / "skills" / "zoen.bak",
        root / "plugins" / "zoen-face",
        root / "workspace",
    ):
        dirty = _drop(path) or dirty
    extra = Path("/workspace")
    if extra.is_dir() and Path("/.dockerenv").exists():
        for path in extra.rglob("face.py"):
            dirty = _drop(path) or dirty
    dest_skill = root / "skills" / "zoen"
    dest = (
        dest_skill
        if src.is_dir() and ((src / "scripts").is_dir() or (src / "SKILL.md").is_file())
        else dest_skill / "scripts"
    )
    stale_root = dest_skill / "face.py"
    if dest != dest_skill and stale_root.is_file():
        stale_root.unlink()
        dirty = True
    if src.is_dir() and not _same_tree(src, dest):
        _install_skill(src, dest)
        dirty = True
    if dirty:
        _drop(root / "zoen" / "BOOTSTRAP.md")
        _drop(root / "zoen" / "VOICE.md")
    return dirty


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    refresh_image_scripts()
    if args:
        for raw in args:
            path = Path(raw)
            if path.name == "config.yaml":
                refresh_image_scripts(str(path.resolve().parent))
            ensure(path)
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
