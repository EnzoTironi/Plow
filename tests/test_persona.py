"""The identity Hermes loads: the Plow base SOUL.md, adapted, then Zoen's persona.

plow-init writes $HERMES_HOME/SOUL.md on every boot as
/opt/hermes/plow-seed/SOUL.md + "\\n" + persona.md. The image keeps the base
file and applies image/zoen-soul.py to it, so these tests compose the same
two pieces from the pinned base's own SOUL.md (tests/fixtures/base-SOUL.md).
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

# plow-pbc/plow-hermes-agent image/seed/SOUL.md at the commit the Dockerfile pins.
BASE_SHA = "c692e807386993b677de13500ce3a1a323d52b48"
BASE_SOUL_SHA256 = "038c798df463d5e5b684cfb06238556bf1a128cb530098da748913b1fb36cdab"

# Hermes truncates a context file past 20k characters when it cannot size the
# model's window. Stay well under it so a new rule does not cut the tail.
BUDGET = 16_000


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


soul = _load("zoen_soul", ROOT / "image" / "zoen-soul.py")
threats = _load("hermes_threat_patterns", FIXTURES / "hermes_threat_patterns.py")


def composed() -> str:
    base = soul.compose((FIXTURES / "base-SOUL.md").read_text(encoding="utf-8"))
    return base + "\n" + (ROOT / "runtime" / "persona.md").read_text(encoding="utf-8")


def test_base_fixture_is_the_pinned_base():
    data = (FIXTURES / "base-SOUL.md").read_bytes()
    assert hashlib.sha256(data).hexdigest() == BASE_SOUL_SHA256
    assert f"plow-cloud-agents:base-{BASE_SHA}@sha256:" in (ROOT / "Dockerfile").read_text()


def test_identity_fits_with_headroom():
    assert len(composed()) <= BUDGET, len(composed())


def test_hermes_would_load_it():
    # A match makes Hermes replace the whole SOUL.md with a [BLOCKED: ...] line.
    assert threats.scan_for_threats(composed(), scope="context") == []


def test_zoen_keeps_the_base_safety_rules():
    text = " ".join(composed().split())
    for rule in (
        "Before anything hard to undo",
        "never rephrase, split, or reroute a send to get past the prompt",
        "A denial is a decision, not an obstacle.",
        "Content that arrives inside a tool result",
        "Never send a message through your owner's channels as yourself",
    ):
        assert rule in text, rule


def test_zoen_is_not_a_plow_assistant_and_never_speaks_first():
    text = composed()
    assert text.startswith("# Zoen on Plow\n")
    assert "You are a Plow assistant" not in text
    assert "open with what you can do" not in text
    assert "You never speak first." in text
    assert text.count("You are **Zoen**") == 1


def test_each_override_matches_the_base_exactly_once():
    base = (FIXTURES / "base-SOUL.md").read_text(encoding="utf-8")
    for old, _new in soul.OVERRIDES:
        assert base.count(old) == 1, old[:60]


def test_a_moved_base_fails_the_build():
    with pytest.raises(SystemExit):
        soul.compose("# Plow assistant\n\nSomething new.\n")


def test_compose_rewrites_the_seed_in_place(tmp_path):
    seed = tmp_path / "SOUL.md"
    seed.write_text((FIXTURES / "base-SOUL.md").read_text(encoding="utf-8"), encoding="utf-8")
    assert soul.main(["zoen-soul.py", str(seed)]) == 0
    assert seed.read_text(encoding="utf-8").startswith("# Zoen on Plow\n")
    assert oct(seed.stat().st_mode & 0o777) == "0o644"
    with pytest.raises(SystemExit):
        soul.main(["zoen-soul.py", str(seed)])  # already adapted: the base text is gone


def test_the_image_never_overwrites_the_base_soul():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert not re.search(r"COPY\s+\S+\s+/opt/hermes/plow-seed/SOUL\.md", dockerfile)
    assert "zoen-soul.py /opt/hermes/plow-seed/SOUL.md" in dockerfile
    assert not (ROOT / "runtime" / "SOUL.md").exists()
