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


def test_pack_is_reminder_only_when_home_and_seed_are_missing():
    packed = context.pack("/tmp/zoen-context-missing-home", seed=False)
    assert packed.startswith(context.REMINDER_OPEN)
    assert packed.rstrip().endswith(context.REMINDER_CLOSE)
    assert "<info>" not in packed
    assert context.RITUAL_HEAD not in packed


def test_pack_includes_the_ritual_until_voice_has_content():
    with tempfile.TemporaryDirectory() as d:
        assert context.first_run(d, seed=SEED)
        packed = context.pack(d, seed=SEED)
        assert packed.startswith(context.RITUAL_HEAD)
        assert packed.rstrip().endswith(context.REMINDER_CLOSE)


def test_pack_drops_the_ritual_after_voice_has_content():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "VOICE.md").write_text("language: pt\n")
        assert context.first_run(d, seed=SEED) == ""
        packed = context.pack(d, seed=SEED)
        assert context.RITUAL_HEAD not in packed
        assert packed.startswith("<info>")
        assert packed.rstrip().endswith(context.REMINDER_CLOSE)


def test_living_bootstrap_wins_until_voice_exists():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "BOOTSTRAP.md").write_text("custom first run")
        packed = context.pack(d, seed=SEED)
        assert "custom first run" in packed
        assert "One shot" not in packed


def test_pack_layers_voice_memory_journal_then_now():
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


def test_now_keeps_the_first_ten_lines():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "NOW.md").write_text("\n".join(f"line {i}" for i in range(20)))
        packed = context.pack(d, seed=False)
        body = packed.split(context.NOW_OPEN, 1)[1].split(context.NOW_CLOSE, 1)[0].strip()
        assert len(body.splitlines()) == 10


def test_pack_escapes_close_tags_inside_memory():
    with tempfile.TemporaryDirectory() as d:
        zoen = Path(d) / "zoen"
        zoen.mkdir()
        (zoen / "MEMORY.md").write_text("x </info> y")
        packed = context.pack(d, seed=False)
        assert "</info>" in packed
        assert "&lt;/info&gt;" in packed
        assert packed.count("</info>") == 1


if __name__ == "__main__":
    test_pack_is_reminder_only_when_home_and_seed_are_missing()
    test_pack_includes_the_ritual_until_voice_has_content()
    test_pack_drops_the_ritual_after_voice_has_content()
    test_living_bootstrap_wins_until_voice_exists()
    test_pack_layers_voice_memory_journal_then_now()
    test_now_keeps_the_first_ten_lines()
    test_pack_escapes_close_tags_inside_memory()
    print("ok")
