#!/usr/bin/env python3
"""Keep the Zoen floor cron registered and aimed at the owner's chat.

`hermes cron` keeps jobs in /var/lib/hermes/cron/jobs.json and nothing replays
them on a fresh home, so the supervisor makes sure the one job exists. The home
also outlives a re-mint, so an existing job whose delivery target is not the
current home channel gets retargeted rather than trusted.

Never read "could not tell what is registered" as "nothing is": that duplicates
the job. Only a missing jobs.json means empty; anything unreadable raises.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERMES = "/opt/hermes/bin/hermes"
JOBS_FILE = str(Path(os.environ.get("HERMES_HOME", "/var/lib/hermes")) / "cron/jobs.json")
NAME = "zoen-floor"
SCHEDULE = "0 */2 * * *"
PROMPT = (
    "Run skill zoen, cron section. Keep the existing voice. Read context.py dump and "
    "the native Kanban's active tasks. Resume only work the owner already authorized; "
    "respect cancellation, task scope, account and deadline. Check pending connections "
    "with connect.py status and resume only after the expected account is connected. "
    "Use dedicated cron jobs for actual reminders, not this maintenance cadence. "
    "Preserve legacy software work named in NOW.md or GITHUB_REPO: use the software "
    "maintenance section for those tasks only. Never invent a project or scan unrelated repos. "
    "Notify via plow_send_sequence only for a completed result, a meaningful change, "
    "failure or required input. If nothing needs them, [SILENT]. No periodic check-in. "
    "Never onboard, install, use Latch, spend money or deploy production from cron. "
    "Use their language and casing. Short bubbles, same personality."
)


def registered(jobs_path=JOBS_FILE):
    """The zoen-floor job as hermes persisted it, or None when there is none."""
    try:
        with open(jobs_path) as f:
            jobs = json.load(f)["jobs"]
    except FileNotFoundError:
        return None
    return next((job for job in jobs if job["name"] == NAME), None)


def delivery_target(home_channel):
    if not (home_channel or "").strip():
        raise SystemExit(
            "zoen-floor: PLOW_HOME_CHANNEL is blank; refusing a cron that delivers nowhere"
        )
    return f"plow_chat:{home_channel.strip()}"


def main(home_channel, jobs_path=JOBS_FILE, run=subprocess.run):
    deliver = delivery_target(home_channel)
    job = registered(jobs_path)
    if job is None:
        return run(
            [
                HERMES,
                "cron",
                "create",
                SCHEDULE,
                PROMPT,
                "--name",
                NAME,
                "--skill",
                "zoen",
                "--deliver",
                deliver,
            ]
        ).returncode
    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        schedule = schedule.get("expr")
    changes = []
    for flag, actual, desired in (("--deliver", job.get("deliver"), deliver),
                                   ("--prompt", job.get("prompt"), PROMPT),
                                   ("--schedule", schedule, SCHEDULE)):
        if actual != desired:
            changes.extend((flag, desired))
    if not changes:
        print(f"zoen-floor: already registered for {deliver}")
        return 0
    return run(
        [HERMES, "cron", "edit", job["id"], *changes]
    ).returncode


if __name__ == "__main__":
    sys.exit(main(os.environ.get("PLOW_HOME_CHANNEL", "")))
