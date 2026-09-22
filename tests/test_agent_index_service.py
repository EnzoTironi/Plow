#!/usr/bin/env python3
"""Run: python3 tests/test_agent_index_service.py (no dependencies)."""
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICE = ROOT / "image/s6-overlay/s6-rc.d/agent-index"


def test_wiring():
    # The base image ships the usage reporter; a copy here would shadow it.
    assert not SERVICE.exists()
    assert not (ROOT / "image/s6-overlay/s6-rc.d/user/contents.d/agent-index").exists()
    assert (ROOT / "image/s6-overlay/s6-rc.d/user/contents.d/zoen-floor-cron").exists()
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "vendor/client.pin" not in dockerfile
    assert "lid.176.ftz" not in dockerfile
    assert "fasttext" not in dockerfile
    assert "chromium" not in dockerfile
    assert "faster-whisper" not in dockerfile
    assert "cloudflared" not in dockerfile
    assert "npm install" not in dockerfile
    assert "gh" in dockerfile
    assert "ZOEN_OAUTH_RELAY_URL=" in dockerfile
    assert "zoen-config.yaml" not in dockerfile
    assert "sitecustomize" not in dockerfile
    assert "COPY skills/zoen/scripts/" in dockerfile
    assert "ENV AGENT_ID=zoen" in dockerfile
    assert "ENV AGENT_NAME=Zoen" in dockerfile
    assert "ENV AGENT_BLURB=" in dockerfile
    assert "base-ef0019372ff8bca593611b31ebd2e08f9f1458ff" in dockerfile
    assert "sha256:a8a2f97ad78b8192d80a984dce81d3bf5a9a883d18cb7b677704913a09b56aee" in dockerfile
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
    test_gitignore_blocks_credentials()
    test_stories_and_install_lead_with_one_click()
    time.sleep(0)
    print("ok")
