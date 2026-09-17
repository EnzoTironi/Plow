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
    run = (SERVICE / "run").read_text()
    assert "PLOW_AGENT_TOKEN" + "=" not in run
    compose = (ROOT / "compose.yml").read_text()
    assert "AGENT_ID: ${AGENT_ID:-zoen}" in compose
    assert "HERMES_HOME: /var/lib/hermes" in compose
    gitignore = (ROOT / ".gitignore").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text()
    assert "plow-credentials" in gitignore and "plow-credentials" in dockerignore
    assert 'image = "ghcr.io/enzotironi/zoen/all-in-one:v1"' in (
        ROOT / "plow-agents.toml"
    ).read_text()


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
    install = (ROOT / "docs/INSTALL.md").read_text()
    readme = (ROOT / "README.md").read_text()
    share = (ROOT / "docs/SHARE.md").read_text()
    for text in (install, readme, share):
        assert cta in text
        assert "Deploy" in text
        assert text.find(cta) < text.find("curl")
        assert "TODO(enzo)" not in text
    assert cta in (ROOT / "docs/stories.json").read_text()


if __name__ == "__main__":
    test_wiring()
    test_stands_down_without_agent_id()
    test_gitignore_blocks_credentials()
    test_stories_and_install_lead_with_one_click()
    time.sleep(0)
    print("ok")
