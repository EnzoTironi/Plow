#!/usr/bin/env python3
"""Run: python3 tests/test_register_cron.py"""
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


def fake_run(calls):
    return lambda argv: calls.append(argv) or type("P", (), {"returncode": 0})()


def test_creates_the_floor_cron_on_the_home_channel():
    calls = []
    with tempfile.TemporaryDirectory() as d:
        jobs = pathlib.Path(d, "jobs.json")
        assert rc.main("cht_1", jobs, fake_run(calls)) == 0
    assert calls[-1][:3] == [rc.HERMES, "cron", "create"]
    assert calls[-1][-1] == "plow_chat:cht_1"
    assert "0 */2 * * *" in calls[-1]
    assert "--skill" in calls[-1] and "zoen" in calls[-1]


def test_skips_create_when_the_job_already_targets_that_chat():
    calls = []
    with tempfile.TemporaryDirectory() as d:
        jobs = pathlib.Path(d, "jobs.json")
        jobs.write_text(
            json.dumps(
                {
                    "jobs": [
                        {"id": "j1", "name": "zoen-floor", "deliver": "plow_chat:cht_1"}
                    ]
                }
            )
        )
        assert rc.main("cht_1", jobs, fake_run(calls)) == 0
    assert calls == []


def test_retargets_the_job_when_the_home_chat_moved():
    calls = []
    with tempfile.TemporaryDirectory() as d:
        jobs = pathlib.Path(d, "jobs.json")
        jobs.write_text(
            json.dumps(
                {
                    "jobs": [
                        {"id": "j1", "name": "zoen-floor", "deliver": "plow_chat:cht_1"}
                    ]
                }
            )
        )
        assert rc.main("cht_2", jobs, fake_run(calls)) == 0
    assert calls == [[rc.HERMES, "cron", "edit", "j1", "--deliver", "plow_chat:cht_2"]]


def test_refuses_corrupt_jobs_json():
    calls = []
    with tempfile.TemporaryDirectory() as d:
        jobs = pathlib.Path(d, "jobs.json")
        jobs.write_text("{not json")
        try:
            rc.main("cht_1", jobs, fake_run(calls))
        except json.JSONDecodeError:
            return
    raise AssertionError("corrupt jobs.json was read as empty")


def test_refuses_a_blank_channel():
    with tempfile.TemporaryDirectory() as d:
        jobs = pathlib.Path(d, "jobs.json")
        try:
            rc.main("  ", jobs, fake_run([]))
        except SystemExit:
            return
    raise AssertionError("blank channel accepted")


if __name__ == "__main__":
    test_creates_the_floor_cron_on_the_home_channel()
    test_skips_create_when_the_job_already_targets_that_chat()
    test_retargets_the_job_when_the_home_chat_moved()
    test_refuses_corrupt_jobs_json()
    test_refuses_a_blank_channel()
    print("ok")
