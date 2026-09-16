#!/usr/bin/env python3
"""Run: python3 tests/test_memory.py"""
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("memory", ROOT / "skills/zoen/scripts/memory.py")
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


def test_remember_and_recall():
    with tempfile.TemporaryDirectory() as d:
        wrote = memory.remember(["Enzo prefers lowercase", "cli in this folder"], home=d)
        assert wrote["ok"] is True
        assert wrote["wrote"] == 2
        path = Path(d) / "zoen" / "MEMORY.md"
        text = path.read_text()
        assert "Enzo prefers lowercase" in text
        assert "cli in this folder" in text
        found = memory.recall("enzo lowercase", home=d)
        assert found["ok"] is True
        assert any("Enzo prefers lowercase" in hit["text"] for hit in found["hits"])


def test_recall_misses_empty_home():
    with tempfile.TemporaryDirectory() as d:
        found = memory.recall("enzo", home=d)
        assert found["ok"] is True
        assert found["hits"] == []


def test_remember_requires_a_fact():
    with tempfile.TemporaryDirectory() as d:
        wrote = memory.remember(["  "], home=d)
        assert wrote["ok"] is False


if __name__ == "__main__":
    test_remember_and_recall()
    test_recall_misses_empty_home()
    test_remember_requires_a_fact()
    print("ok")
