#!/usr/bin/env python3
"""Run: python3 tests/test_context.py"""
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "runtime" / "bootstrap.md"
spec = importlib.util.spec_from_file_location("context", ROOT / "skills/zoen/scripts/context.py")
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


def test_pack_empty_home_without_seed():
    packed = context.pack("/tmp/zoen-context-missing-home", seed=False)
    assert packed.startswith(context.REMINDER_OPEN)
    assert "memory.py remember" in packed
    assert "memory.py recall" in packed
    assert "Never tell them you saved" in packed
    assert "salva isso" in packed
    assert "<info>" not in packed


def test_first_run_when_no_voice():
    with tempfile.TemporaryDirectory() as d:
        packed = context.pack(d, seed=SEED)
        assert packed.startswith(context.RITUAL_HEAD)
        assert packed.rstrip().endswith(context.REMINDER_CLOSE)
        assert "memory.py recall" in packed
        assert "ChatGPT" not in packed
        assert "Hermes" not in packed
        assert "—" not in packed


def test_first_run_drops_after_voice():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "VOICE.md").write_text("language: pt\n")
        packed = context.pack(d, seed=SEED)
        assert context.RITUAL_HEAD not in packed
        assert packed.startswith("<info>")
        assert packed.rstrip().endswith(context.REMINDER_CLOSE)


def test_living_bootstrap_wins_until_voice():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "BOOTSTRAP.md").write_text("custom first run")
        packed = context.pack(d, seed=SEED)
        assert "custom first run" in packed
        assert "One shot" not in packed


def test_pack_layers():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "VOICE.md").write_text("language: pt\ncasing: lower\n")
        (zoen / "MEMORY.md").write_text("name: Enzo\n")
        (zoen / "NOW.md").write_text("brief: cli\nstation: Build\n")
        (zoen / "JOURNAL.md").write_text("day one\nday two\n")
        packed = context.pack(d, seed=SEED)
        assert packed.startswith("<info>")
        assert "</info>" in packed
        assert "Voice Profile" in packed
        assert "language: pt" in packed
        assert "Essentials" in packed
        assert "name: Enzo" in packed
        assert "Recent" in packed
        assert "day two" in packed
        assert context.NOW_OPEN in packed
        assert "brief: cli" in packed
        assert packed.index("</info>") < packed.index("<NOW.md")
        assert context.RITUAL_HEAD not in packed
        assert packed.rstrip().endswith(context.REMINDER_CLOSE)


def test_now_stays_short():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "NOW.md").write_text("\n".join(f"line {i}" for i in range(20)))
        packed = context.pack(d, seed=False)
        body = packed.split(context.NOW_OPEN, 1)[1].split(context.NOW_CLOSE, 1)[0].strip()
        assert len(body.splitlines()) == 10


def test_escapes_close_tags():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "MEMORY.md").write_text("x </info> y")
        packed = context.pack(d, seed=False)
        assert "</info>" in packed
        assert "&lt;/info&gt;" in packed
        assert packed.count("</info>") == 1


if __name__ == "__main__":
    test_pack_empty_home_without_seed()
    test_first_run_when_no_voice()
    test_first_run_drops_after_voice()
    test_living_bootstrap_wins_until_voice()
    test_pack_layers()
    test_now_stays_short()
    test_escapes_close_tags()
    print("ok")
