#!/usr/bin/env python3
"""Run: python3 tests/test_agent_index_service.py (no dependencies)."""
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICE = ROOT / "image/s6-overlay/s6-rc.d/agent-index"


def test_wiring():
    assert (SERVICE / "type").read_text().strip() == "longrun"
    assert (SERVICE / "dependencies.d/plow-init").exists()
    assert (ROOT / "image/s6-overlay/s6-rc.d/user/contents.d/agent-index").exists()
    assert (ROOT / "image/s6-overlay/s6-rc.d/user/contents.d/zoen-floor-cron").exists()
    pin = (ROOT / "vendor/client.pin").read_text()
    assert re.search(r"^sha=[0-9a-f]{40}$", pin, re.M)
    assert re.search(r"^sha256=[0-9a-f]{64}$", pin, re.M)
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "vendor/client.pin" in dockerfile and "sha256sum" in dockerfile
    assert "lid.176.ftz" in dockerfile
    assert "COPY skills/zoen/scripts/" in dockerfile
    assert "ENV AGENT_ID=zoen" in dockerfile
    assert "ENV AGENT_NAME=Zoen" in dockerfile
    assert "ENV AGENT_BLURB=" in dockerfile
    assert "base-42cb36ed16f513e9c7461b3f355acec181c8a26d" in dockerfile
    assert "sha256:7bb771761c075ef3736c4cc7bdc48402ce325ed35b5efb529b1b31ec7956fd40" in dockerfile
    run = (SERVICE / "run").read_text()
    assert "#!/command/with-contenv" not in run
    assert "env -i" not in run
    assert "PLOW_AGENT_TOKEN=" not in run
    assert "container_environment/PLOW_API_BASE" in run
    assert run.count("/opt/plow/agent-index-client.py") == 3
    assert run.count('PLOW_API_BASE="$PLOW_API_BASE"') == 3
    assert run.count("/bin/sleep 300") == 3
    assert "--name" in run and "--blurb" in run
    assert 'set -- --register --agent "$AGENT_ID"' in run
    compose = (ROOT / "compose.yml").read_text()
    assert "AGENT_ID: ${AGENT_ID:-zoen}" in compose
    assert "AGENT_NAME: ${AGENT_NAME:-Zoen}" in compose
    assert "HERMES_HOME: /var/lib/hermes" in compose
    gitignore = (ROOT / ".gitignore").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text()
    assert "plow-credentials" in gitignore and "plow-credentials" in dockerignore
    assert 'image = "ghcr.io/enzotironi/zoen/all-in-one:v1"' in (
        ROOT / "plow-agents.toml"
    ).read_text()


def test_register_argv_is_built_as_the_shell_builds_it():
    block = (SERVICE / "run").read_text()
    block = block[block.index("set -- --register"):block.index("while :; do")]
    script = block + '\nfor a in "$@"; do printf "%s\\n" "$a"; done\n'
    cases = [
        ({"AGENT_ID": "my-agent"},
         ["--register", "--agent", "my-agent"]),
        ({"AGENT_ID": "my-agent", "AGENT_NAME": "My Agent"},
         ["--register", "--agent", "my-agent", "--name", "My Agent"]),
        ({"AGENT_ID": "my-agent", "AGENT_NAME": "My Agent",
          "AGENT_BLURB": "One line about it"},
         ["--register", "--agent", "my-agent", "--name", "My Agent",
          "--blurb", "One line about it"]),
        ({"AGENT_ID": "my-agent", "AGENT_NAME": "", "AGENT_BLURB": ""},
         ["--register", "--agent", "my-agent"]),
    ]
    for environment, expected in cases:
        result = subprocess.run(["sh", "-c", script], env=environment,
                                capture_output=True, text=True, check=True)
        assert result.stdout.splitlines() == expected, environment


def test_stands_down_without_agent_id():
    script = (SERVICE / "run").read_text()
    with tempfile.TemporaryDirectory() as d:
        sandbox = pathlib.Path(d) / "run.sh"
        sandbox.write_text(script)
        sandbox.chmod(0o755)
        env = {"PATH": os.environ["PATH"], "PLOW_AGENT_TOKEN": "plow_atokenshapedthing"}
        try:
            done = subprocess.run(["sh", str(sandbox)], capture_output=True,
                                  timeout=2, env=env)
            said = (done.stdout or b"") + (done.stderr or b"")
        except subprocess.TimeoutExpired as expired:
            said = (expired.stdout or b"") + (expired.stderr or b"")
        text = said.decode() if isinstance(said, bytes) else said
        assert "standing down" in text
        assert "AGENT_ID" in text


def test_gitignore_blocks_credentials():
    gi = (ROOT / ".gitignore").read_text().splitlines()
    di = (ROOT / ".dockerignore").read_text().splitlines()
    assert "plow-credentials" in gi or "/plow-credentials" in gi
    assert "plow-credentials" in di or "/plow-credentials" in di


def test_stories_and_install_lead_with_one_click():
    stories = json.loads((ROOT / "docs/stories.json").read_text())
    assert stories
    seen = set()
    for story in stories:
        assert story["id"] and story["id"] not in seen
        seen.add(story["id"])
        assert story["title"] and story["body"] and story["tag"]
    assert "three-tickets-one-dream" in seen
    assert "waitlist-two-screens" in seen
    assert "broke-then-fixed" in seen
    cta = "https://aiworthusing.com/agent-index/zoen"
    sms = "sms:+16282463032?&body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen"
    install = (ROOT / "docs/INSTALL.md").read_text()
    readme = (ROOT / "README.md").read_text()
    share = (ROOT / "docs/SHARE.md").read_text()
    for text in (install, readme, share):
        assert cta in text
        assert "Text this agent" in text
        assert sms in text
        assert "Set this up for me: aiworthusing.com/agent-index/zoen" in text
        assert text.find(cta) < text.find("curl")
        assert "TODO(enzo)" not in text
    stories = (ROOT / "docs/stories.json").read_text()
    assert cta in stories
    assert "Text this agent" in stories


if __name__ == "__main__":
    test_wiring()
    test_register_argv_is_built_as_the_shell_builds_it()
    test_stands_down_without_agent_id()
    test_gitignore_blocks_credentials()
    test_stories_and_install_lead_with_one_click()
    time.sleep(0)
    print("ok")
