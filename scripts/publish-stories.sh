#!/bin/sh
# Publish the stories in docs/stories.json to the Agent Index.
# Needs the container running (after plow-agents mint + compose up) so the
# reporter has already exchanged PLOW_AGENT_TOKEN for its aik_ key.
set -eu
cd "$(dirname "$0")/.."

python3 - "$PWD/docs/stories.json" <<'PY'
import json, pathlib, subprocess, sys
stories = json.loads(pathlib.Path(sys.argv[1]).read_text())
for story in stories:
    cmd = [
        "docker", "compose", "exec", "-T", "--user", "hermes",
        "-e", "HOME=/var/lib/hermes",
        "-e", "HERMES_HOME=/var/lib/hermes",
        "-e", "AGENT_ID=zoen",
        "agent",
        "/opt/hermes/.venv/bin/python3", "/opt/plow/agent-index-client.py",
        "--agent", "zoen",
        "--story", story["id"],
        "--title", story["title"],
        "--body", story["body"],
        "--tag", story["tag"],
    ]
    if story.get("image"):
        cmd.extend(["--image", story["image"]])
    for url in story.get("images") or []:
        cmd.extend(["--image", url])
    print("+", story["id"], flush=True)
    subprocess.check_call(cmd)
print("ok", len(stories), "stories")
PY
