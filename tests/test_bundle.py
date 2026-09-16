#!/usr/bin/env python3
"""Run: python3 tests/test_bundle.py (no dependencies)."""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "skills/zoen/scripts/bundle.py"
FIXTURES = ROOT / "tests/fixtures"

spec = importlib.util.spec_from_file_location("bundle", BUNDLE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_harvest_and_pack():
    cands = mod.harvest_deepsec(FIXTURES / "deepsec")
    assert len(cands) == 1
    assert cands[0]["path"] == "auth.py"
    assert cands[0]["vuln_slug"] == "hardcoded-secret"
    assert cands[0]["lines"] == [18]

    preview = json.loads((FIXTURES / "preview.json").read_text())
    rules = json.loads((FIXTURES / "rules.json").read_text())
    files = mod.preview_files(preview)
    groups = mod.rule_groups(rules)
    tasks, overflow = mod.pack(files, groups, cands, max_tasks=10)
    kinds = {t["kind"] for t in tasks}
    assert kinds == {"ocr-bundle"}
    assert overflow == []
    auth = next(t for t in tasks if "auth.py" in t["files"])
    assert auth["candidates"][0]["vuln_slug"] == "hardcoded-secret"
    assert "dismissed" in auth["prompt"]


def test_overflow_keeps_second_lot():
    files = [{"path": f"f{i}.py", "status": "modified", "insertions": 1, "deletions": 0} for i in range(12)]
    tasks, overflow = mod.pack(files, [], [], max_tasks=10)
    assert len(tasks) == 10
    assert len(overflow) == 2
    assert overflow == ["f10.py", "f11.py"]


def test_cli_fixtures():
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        proc = subprocess.run(
            [
                sys.executable,
                str(BUNDLE),
                "--repo",
                str(repo),
                "--preview-json",
                str(FIXTURES / "preview.json"),
                "--rules-json",
                str(FIXTURES / "rules.json"),
                "--deepsec-data",
                str(FIXTURES / "deepsec"),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["tools"]["ocr"] is True
        assert payload["tools"]["deepsec"] is True
        assert payload["mode"] == "range"
        assert len(payload["tasks"]) >= 2
        assert payload["overflow_files"] == []
        paths = {f["path"] for f in payload["files"]}
        assert paths == {"app.py", "auth.py", "util.py"}


def test_max_tasks_rejects_zero():
    try:
        mod.pack([], [], [], max_tasks=0)
    except mod.ToolError:
        return
    raise AssertionError("max_tasks=0 must fail")


if __name__ == "__main__":
    test_harvest_and_pack()
    test_overflow_keeps_second_lot()
    test_cli_fixtures()
    test_max_tasks_rejects_zero()
    print("ok")
