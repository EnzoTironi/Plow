#!/usr/bin/env python3
"""Run: python3 tests/test_register_cron.py (no dependencies)."""
import importlib.util
import json
import pathlib
import tempfile

spec = importlib.util.spec_from_file_location(
    "register_cron",
    pathlib.Path(__file__).parent.parent / "skills/zoen/scripts/register_cron.py",
)
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

calls = []
fake_run = lambda argv: calls.append(argv) or type("P", (), {"returncode": 0})()

with tempfile.TemporaryDirectory() as d:
    jobs = pathlib.Path(d, "jobs.json")

    assert rc.main("cht_1", jobs, fake_run) == 0
    assert calls[-1][:3] == [rc.HERMES, "cron", "create"]
    assert calls[-1][-1] == "plow_chat:cht_1" and "0 */2 * * *" in calls[-1]
    assert "--skill" in calls[-1] and "zoen" in calls[-1]
    assert "NOW.md" in rc.PROMPT
    assert "context.py dump" in rc.PROMPT
    assert "First-Run Ritual" in rc.PROMPT
    assert "end of a bubble" in rc.PROMPT
    assert "only notifies" in rc.PROMPT
    assert "Do not re-ask" in rc.PROMPT
    assert "plow_send_sequence" in rc.PROMPT
    assert "1.75" in rc.PROMPT
    assert "pictures and video" in rc.PROMPT
    assert "Portuguese" in rc.PROMPT
    assert "gh pr list" in rc.PROMPT
    assert "never Latch" in rc.PROMPT
    assert "Never send https://plow.co/latch" in rc.PROMPT
    assert "High risk" in rc.PROMPT
    assert "GitHub issues" in rc.PROMPT

    jobs.write_text(json.dumps({"jobs": [{"id": "j1", "name": "zoen-floor", "deliver": "plow_chat:cht_1"}]}))
    calls.clear()
    assert rc.main("cht_1", jobs, fake_run) == 0 and calls == []

    assert rc.main("cht_2", jobs, fake_run) == 0
    assert calls == [[rc.HERMES, "cron", "edit", "j1", "--deliver", "plow_chat:cht_2"]]

    jobs.write_text("{not json")
    try:
        rc.main("cht_1", jobs, fake_run)
        raise AssertionError("corrupt jobs.json was read as empty")
    except json.JSONDecodeError:
        pass

    jobs.unlink()
    try:
        rc.main("  ", jobs, fake_run)
        raise AssertionError("blank channel accepted")
    except SystemExit:
        pass

print("ok")
