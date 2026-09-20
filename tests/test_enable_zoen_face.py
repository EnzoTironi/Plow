#!/usr/bin/env python3
"""Run: python3 tests/test_enable_zoen_face.py"""
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "enable_zoen_face", ROOT / "image/enable-zoen-face.py"
)
enable = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enable)

LIVE = """mcp_servers:
  plow:
    enabled: true
plugins:
  enabled:
  - plow-chat-platform
  entries:
    plow-chat-platform:
      allow_tool_override: false
_config_version: 44
"""
VOICED = """plugins:
  enabled:
  - plow-chat-platform
  - zoen-face
"""

SEED = """plugins:
  enabled:
    - plow-chat-platform
    - other
"""


def _write(folder: str, name: str, text: str) -> Path:
    path = Path(folder) / name
    path.write_text(text)
    return path


def test_live_dump_gains_zoen_face_and_keeps_plow_chat():
    with tempfile.TemporaryDirectory() as folder:
        path = _write(folder, "config.yaml", LIVE)
        assert enable.ensure(path) is True
        text = path.read_text()
        assert enable.ensure(path) is False
    assert "- zoen-face" in text
    assert text.index("plow-chat-platform") < text.index("zoen-face")
    assert "mcp_servers:" in text
    assert "_config_version: 44" in text
    if enable.yaml is not None:
        data = enable.yaml.safe_load(text)
        assert data["approvals"]["mode"] == "off"
        assert data["security"]["tirith_enabled"] is False
        assert data["display"]["interim_assistant_messages"] is False
        assert data["display"]["platforms"]["plow_chat"]["long_running_notifications"] is False
        assert data["model"]["default"] == "openai/gpt-5.6-luna"
        assert "openai/gpt-5.6-luna" in data["providers"]["plow"]["models"]


def test_apply_runtime_turns_yolo_on_and_quiets_plow_chat():
    data = {"plugins": {"enabled": ["plow-chat-platform"]}}
    assert enable.apply_runtime(data) is True
    assert data["approvals"]["mode"] == "off"
    assert data["approvals"]["cron_mode"] == "approve"
    assert data["security"]["tirith_enabled"] is False
    assert data["display"]["interim_assistant_messages"] is False
    assert data["display"]["platforms"]["plow_chat"]["long_running_notifications"] is False
    assert data["busy_input_mode"] == "steer"
    assert data["busy_ack_enabled"] is False
    assert enable.apply_runtime(data) is False


def test_apply_runtime_pins_talker_and_leaf_catalog():
    data = {
        "model": {"default": "z-ai/glm-5.2", "provider": "plow"},
        "providers": {
            "plow": {"models": {"z-ai/glm-5.2": {"prompt_caching": True}}}
        },
    }
    assert enable.apply_runtime(data) is True
    assert data["model"]["default"] == "openai/gpt-5.6-luna"
    assert data["model"]["provider"] == "plow"
    models = data["providers"]["plow"]["models"]
    assert models["z-ai/glm-5.2"]["prompt_caching"] is True
    for slug in (
        "anthropic/claude-sonnet-5",
        "anthropic/claude-opus-5",
        "openai/gpt-5.6-luna",
        "moonshotai/kimi-k3",
    ):
        assert slug in models
    assert data["auxiliary"]["vision"]["model"] == "anthropic/claude-sonnet-5"
    assert enable.apply_runtime(data) is False


def test_already_listed_still_gains_yolo():
    if enable.yaml is None:
        return
    with tempfile.TemporaryDirectory() as folder:
        path = _write(folder, "config.yaml", VOICED)
        assert enable.ensure(path) is True
        text = path.read_text()
        data = enable.yaml.safe_load(text)
        assert data["approvals"]["mode"] == "off"
        assert data["busy_input_mode"] == "steer"
        assert "- zoen-face" in text


def test_seed_text_keeps_indent_and_neighbors():
    with tempfile.TemporaryDirectory() as folder:
        path = _write(folder, "config.yaml", SEED)
        assert enable.ensure(path, text_only=True) is True
        assert path.read_text() == (
            "plugins:\n"
            "  enabled:\n"
            "    - plow-chat-platform\n"
            "    - zoen-face\n"
            "    - other\n"
        )


def test_refresh_replaces_stale_home_face_and_reopens_first_contact():
    with tempfile.TemporaryDirectory() as folder:
        bundled = Path(folder) / "bundled"
        bundled.mkdir()
        (bundled / "face.py").write_text("HELLO = ('new',)\n")
        home = Path(folder) / "home"
        scripts = home / "skills" / "zoen" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "face.py").write_text("HELLO = ('old',)\n")
        voice = home / "zoen" / "VOICE.md"
        voice.parent.mkdir(parents=True)
        voice.write_text("language: pt\n")
        (voice.parent / "BOOTSTRAP.md").write_text("old ritual\n")
        assert enable.refresh_image_scripts(
            str(home), bundled=bundled, face=bundled / "face.py"
        ) is True
        assert (scripts / "face.py").read_text() == "HELLO = ('new',)\n"
        assert not voice.exists()
        assert not (home / "zoen" / "BOOTSTRAP.md").exists()
        assert enable.refresh_image_scripts(
            str(home), bundled=bundled, face=bundled / "face.py"
        ) is False
        voice.parent.mkdir(parents=True, exist_ok=True)
        voice.write_text("language: pt\n")
        assert enable.refresh_image_scripts(
            str(home), bundled=bundled, face=bundled / "face.py"
        ) is False
        assert voice.read_text() == "language: pt\n"


def test_refresh_removes_stale_layout_and_bak():
    with tempfile.TemporaryDirectory() as folder:
        bundled = Path(folder) / "bundled"
        (bundled / "scripts").mkdir(parents=True)
        (bundled / "SKILL.md").write_text("name: zoen\n")
        (bundled / "scripts" / "face.py").write_text("HELLO = ('new',)\n")
        home = Path(folder) / "home"
        dest = home / "skills" / "zoen"
        dest.mkdir(parents=True)
        (dest / "face.py").write_text(
            'HELLO = ("a gente te ajuda. +55 31 99994-1160",)\n'
        )
        (dest / "scripts").mkdir()
        (dest / "scripts" / "face.py").write_text("HELLO = ('old',)\n")
        bak = home / "skills" / "zoen.bak"
        bak.mkdir()
        (bak / "face.py").write_text("old\n")
        plugin = home / "plugins" / "zoen-face"
        plugin.mkdir(parents=True)
        (plugin / "presence.py").write_text("kick\n")
        assert enable.refresh_image_scripts(
            str(home), bundled=bundled, face=bundled / "scripts" / "face.py"
        ) is True
        assert (dest / "scripts" / "face.py").read_text() == "HELLO = ('new',)\n"
        assert (dest / "SKILL.md").read_text() == "name: zoen\n"
        assert not (dest / "face.py").exists()
        assert not bak.exists()
        assert not plugin.exists()


def test_refresh_keeps_voice_when_official_face_is_already_there():
    with tempfile.TemporaryDirectory() as folder:
        bundled = Path(folder) / "bundled"
        bundled.mkdir()
        (bundled / "face.py").write_text("HELLO = ('new',)\n")
        home = Path(folder) / "home"
        scripts = home / "skills" / "zoen" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "face.py").write_text("HELLO = ('new',)\n")
        voice = home / "zoen" / "VOICE.md"
        voice.parent.mkdir(parents=True)
        voice.write_text("language: pt\n")
        assert enable.refresh_image_scripts(
            str(home), bundled=bundled, face=bundled / "face.py"
        ) is False
        assert voice.read_text() == "language: pt\n"


def test_refresh_pins_workspace_leftover_face():
    with tempfile.TemporaryDirectory() as folder:
        bundled = Path(folder) / "bundled"
        bundled.mkdir()
        (bundled / "face.py").write_text("HELLO = ('new',)\n")
        home = Path(folder) / "home"
        workspace = home / "workspace" / "Plow" / "skills" / "zoen" / "scripts"
        workspace.mkdir(parents=True)
        (workspace / "face.py").write_text(
            'HELLO = (f"a gente te ajuda. {ENZO_TEL_DISPLAY}",)\n'
        )
        assert enable.refresh_image_scripts(
            str(home), bundled=bundled, face=bundled / "face.py"
        ) is True
        assert not (home / "workspace").exists()


if __name__ == "__main__":
    test_live_dump_gains_zoen_face_and_keeps_plow_chat()
    test_apply_runtime_turns_yolo_on_and_quiets_plow_chat()
    test_apply_runtime_pins_talker_and_leaf_catalog()
    test_already_listed_still_gains_yolo()
    test_seed_text_keeps_indent_and_neighbors()
    test_refresh_replaces_stale_home_face_and_reopens_first_contact()
    test_refresh_keeps_voice_when_official_face_is_already_there()
    test_refresh_removes_stale_layout_and_bak()
    test_refresh_pins_workspace_leftover_face()
    print("ok")
