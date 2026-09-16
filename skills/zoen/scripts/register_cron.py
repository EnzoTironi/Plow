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

HERMES = "/opt/hermes/bin/hermes"
JOBS_FILE = "/var/lib/hermes/cron/jobs.json"
NAME = "zoen-floor"
SCHEDULE = "0 */2 * * *"
PROMPT = (
    "Run skill zoen, cron section. Face: the owner never sees the machinery. "
    "context.py dump first, then NOW.md. If the dump is a First-Run Ritual "
    "and NOW.md is empty, [SILENT]. Never block; iMessage only "
    "notifies, max two lines per bubble via plow_send_sequence with pauses "
    "1.75s then 2s; more bubbles if needed. Always send pictures and video "
    "(MEDIA: each file its own bubble). watch.py snapshot first. If alerts, "
    "heal the worktree, never Latch never deploy production; open a PR with "
    "zoen-review media if you can; notify then end. Then gh pr list --state open; "
    "for each: gh pr checks and gh pr view --comments. New comments or failing "
    "checks: skill_view babysit and prove in the container, never Latch. Merge "
    "only if NOW risk is low and prove is green. High risk: notify, do not merge "
    "from cron. Else if NOW.md issues or open GitHub issues, continue that station; "
    "if empty and no PR work, [SILENT]. Do not re-ask. Never install. "
    "Never send https://plow.co/latch from cron. Do not name tools or files "
    "in the bubbles. No em dash, no title case, no all caps. match their casing. "
    "lowercase if they do. never a period at the end of a bubble. "
    "Same language as VOICE.md / their last text. Never English after "
    "Portuguese."
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
    if job["deliver"] == deliver:
        print(f"zoen-floor: already registered for {deliver}")
        return 0
    return run(
        [HERMES, "cron", "edit", job["id"], "--deliver", deliver]
    ).returncode


if __name__ == "__main__":
    sys.exit(main(os.environ.get("PLOW_HOME_CHANNEL", "")))
