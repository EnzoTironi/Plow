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
        assert rc.main("cht_1", jobs, fake_run(calls), scripts_dir=pathlib.Path(d, "scripts")) == 0
    assert calls[-1][:3] == [rc.HERMES, "cron", "create"]
    assert calls[-1][calls[-1].index("--deliver") + 1] == "plow_chat:cht_1"
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
                        {"id": "j1", "name": "zoen-floor", "deliver": "plow_chat:cht_1", "prompt": rc.PROMPT, "schedule": {"expr": rc.SCHEDULE}, "monitor_script": rc.MONITOR}
                    ]
                }
            )
        )
        assert rc.main("cht_1", jobs, fake_run(calls), scripts_dir=pathlib.Path(d, "scripts")) == 0
    assert calls == []


def test_retargets_the_job_when_the_home_chat_moved():
    calls = []
    with tempfile.TemporaryDirectory() as d:
        jobs = pathlib.Path(d, "jobs.json")
        jobs.write_text(
            json.dumps(
                {
                    "jobs": [
                        {"id": "j1", "name": "zoen-floor", "deliver": "plow_chat:cht_1", "prompt": rc.PROMPT, "schedule": rc.SCHEDULE, "monitor_script": rc.MONITOR}
                    ]
                }
            )
        )
        assert rc.main("cht_2", jobs, fake_run(calls), scripts_dir=pathlib.Path(d, "scripts")) == 0
    assert calls == [[rc.HERMES, "cron", "edit", "j1", "--deliver", "plow_chat:cht_2"]]


def test_refuses_corrupt_jobs_json():
    calls = []
    with tempfile.TemporaryDirectory() as d:
        jobs = pathlib.Path(d, "jobs.json")
        jobs.write_text("{not json")
        try:
            rc.main("cht_1", jobs, fake_run(calls), scripts_dir=pathlib.Path(d, "scripts"))
        except json.JSONDecodeError:
            return
    raise AssertionError("corrupt jobs.json was read as empty")


def test_refuses_a_blank_channel():
    with tempfile.TemporaryDirectory() as d:
        jobs = pathlib.Path(d, "jobs.json")
        try:
            rc.main("  ", jobs, fake_run([]), scripts_dir=pathlib.Path(d, "scripts"))
        except SystemExit:
            return
    raise AssertionError("blank channel accepted")


def test_reconciles_stale_prompt_and_schedule_without_recreating(tmp_path):
    calls = []
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [{"id": "same-job", "name": rc.NAME,
        "deliver": "plow_chat:cht_1", "prompt": "old software-only prompt",
        "schedule": {"kind": "cron", "expr": "0 0 * * *"}}]}))
    assert rc.main("cht_1", path, fake_run(calls), scripts_dir=tmp_path / "scripts") == 0
    assert calls == [[rc.HERMES, "cron", "edit", "same-job", "--prompt", rc.PROMPT,
                      "--schedule", rc.SCHEDULE, "--monitor-script", rc.MONITOR]]


def test_creates_the_floor_cron_in_monitor_mode(tmp_path):
    calls = []
    scripts = tmp_path / "scripts"
    assert rc.main("cht_1", tmp_path / "jobs.json", fake_run(calls), scripts_dir=scripts) == 0
    argv = calls[-1]
    assert argv[argv.index("--monitor-script") + 1] == rc.MONITOR
    installed = scripts / rc.MONITOR
    assert installed.read_bytes() == rc.MONITOR_SOURCE.read_bytes()
    assert oct(installed.stat().st_mode & 0o777) == "0o644"


def test_an_existing_floor_gains_the_monitor_in_place(tmp_path):
    """Owners who installed before the gate keep their job id; only the monitor is added."""
    calls = []
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [{"id": "kept", "name": rc.NAME,
        "deliver": "plow_chat:cht_1", "prompt": rc.PROMPT, "schedule": rc.SCHEDULE}]}))
    assert rc.main("cht_1", path, fake_run(calls), scripts_dir=tmp_path / "scripts") == 0
    assert calls == [[rc.HERMES, "cron", "edit", "kept", "--monitor-script", rc.MONITOR]]


def test_the_monitor_copy_is_refreshed_and_never_through_a_link(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    elsewhere = tmp_path / "elsewhere.py"
    elsewhere.write_text("print('not ours')\n")
    (scripts / rc.MONITOR).symlink_to(elsewhere)
    assert rc.install_monitor(scripts) is True
    assert not (scripts / rc.MONITOR).is_symlink()
    assert elsewhere.read_text() == "print('not ours')\n"
    assert rc.install_monitor(scripts) is False


if __name__ == "__main__":
    test_creates_the_floor_cron_on_the_home_channel()
    test_skips_create_when_the_job_already_targets_that_chat()
    test_retargets_the_job_when_the_home_chat_moved()
    test_refuses_corrupt_jobs_json()
    test_refuses_a_blank_channel()
    print("ok")
