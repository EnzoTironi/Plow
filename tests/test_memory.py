#!/usr/bin/env python3
"""Run: python3 tests/test_memory.py"""
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("memory", ROOT / "skills/zoen/scripts/memory.py")
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


def test_remember_writes_facts_that_recall_finds():
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


def test_recall_returns_no_hits_in_an_empty_home():
    with tempfile.TemporaryDirectory() as d:
        found = memory.recall("enzo", home=d)
        assert found["ok"] is True
        assert found["hits"] == []


def test_remember_rejects_blank_facts():
    with tempfile.TemporaryDirectory() as d:
        wrote = memory.remember(["  "], home=d)
        assert wrote["ok"] is False


def test_recent_fact_wins_search_ties(tmp_path):
    memory.remember([f"contract deadline {i}" for i in range(20)], home=str(tmp_path))
    found = memory.recall("contract deadline", home=str(tmp_path))
    assert found["hits"][0]["text"].endswith("deadline 19")


def test_correct_and_forget_remove_old_copies(tmp_path):
    home = str(tmp_path)
    memory.remember(["deadline Monday", "unrelated fact"], home=home)
    (tmp_path / "zoen" / "JOURNAL.md").write_text("deadline Monday\nkeep this last line")
    assert memory.revise("deadline Monday", "deadline Friday", home)["changed"] == 2
    assert memory.recall("Monday", home)["hits"] == []
    assert memory.recall("Friday", home)["hits"]
    assert "keep this last line\n- " in (tmp_path / "zoen" / "JOURNAL.md").read_text()
    assert memory.revise("deadline Friday", home=home)["changed"] == 2
    assert memory.recall("Friday", home)["hits"] == []
    assert memory.recall("unrelated", home)["hits"]


if __name__ == "__main__":
    test_remember_writes_facts_that_recall_finds()
    test_recall_returns_no_hits_in_an_empty_home()
    test_remember_rejects_blank_facts()
    print("ok")
