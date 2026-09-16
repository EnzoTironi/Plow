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
        assert "mode: off" in text
        assert "tirith_enabled: false" in text
        assert "interim_assistant_messages: false" in text
        assert "long_running_notifications: false" in text


def test_apply_runtime_turns_yolo_on_and_quiets_plow_chat():
    data = {"plugins": {"enabled": ["plow-chat-platform"]}}
    assert enable.apply_runtime(data) is True
    assert data["approvals"]["mode"] == "off"
    assert data["approvals"]["cron_mode"] == "approve"
    assert data["security"]["tirith_enabled"] is False
    assert data["display"]["interim_assistant_messages"] is False
    assert data["display"]["platforms"]["plow_chat"]["long_running_notifications"] is False
    assert enable.apply_runtime(data) is False


def test_already_listed_still_gains_yolo():
    if enable.yaml is None:
        return
    with tempfile.TemporaryDirectory() as folder:
        path = _write(folder, "config.yaml", VOICED)
        assert enable.ensure(path) is True
        assert "mode: off" in path.read_text()
        assert "- zoen-face" in path.read_text()


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


if __name__ == "__main__":
    test_live_dump_gains_zoen_face_and_keeps_plow_chat()
    test_apply_runtime_turns_yolo_on_and_quiets_plow_chat()
    test_already_listed_still_gains_yolo()
    test_seed_text_keeps_indent_and_neighbors()
    print("ok")
