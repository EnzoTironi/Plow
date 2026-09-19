"""Native task/cron persistence in a disposable image, without a running gateway."""
import json
import os
import subprocess
import tempfile
from pathlib import Path


def hermes(*args):
    result = subprocess.run(["/opt/hermes/.venv/bin/hermes", *args],
                            capture_output=True, text=True, check=True, timeout=20)
    return result.stdout


with tempfile.TemporaryDirectory() as task_home:
    os.environ["HERMES_HOME"] = task_home
    tasks = []
    for title, account in (("Check contract deadline", "google"), ("Plan study week", "none")):
        body = f"Original request: {title}. Source: cht_test. Account: {account}. Next: await owner input."
        created = json.loads(hermes("kanban", "create", title, "--body", body,
                                    "--initial-status", "blocked", "--json"))
        tasks.append(created)
        # A fresh process must recover the full task, not an in-memory projection.
        restored = json.loads(hermes("kanban", "show", created["id"], "--json"))
        assert restored["task"]["body"] == body, restored
    hermes("kanban", "archive", tasks[0]["id"])
    cancelled = json.loads(hermes("kanban", "show", tasks[0]["id"], "--json"))
    retained = json.loads(hermes("kanban", "show", tasks[1]["id"], "--json"))
    assert cancelled["task"]["status"] == "archived", cancelled
    assert retained["task"]["status"] == "blocked", retained

    hermes("cron", "create", "0 0 * * *", "old software-only prompt",
           "--name", "zoen-floor", "--deliver", "plow_chat:cht_old")
    jobs_file = Path(task_home) / "cron/jobs.json"
    original = json.loads(jobs_file.read_text())["jobs"][0]
    os.environ["PLOW_HOME_CHANNEL"] = "cht_test"
    for _ in range(2):
        migrated = subprocess.run(["/opt/hermes/.venv/bin/python", "/opt/plow/zoen/register_cron.py"],
                                  capture_output=True, text=True, timeout=20)
        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    jobs = json.loads(jobs_file.read_text())["jobs"]
    assert len(jobs) == 1 and jobs[0]["id"] == original["id"], jobs
    assert jobs[0]["deliver"] == "plow_chat:cht_test", jobs
    assert jobs[0]["schedule"]["expr"] == "0 */2 * * *", jobs
    assert "native Kanban" in jobs[0]["prompt"], jobs
    assert jobs[0].get("next_run_at"), jobs
    print(json.dumps({"tasks_survive_process_restart": True, "cancellation_isolated": True,
                      "native_cron_migrated_once": True}))
