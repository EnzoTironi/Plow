#!/usr/bin/env python3
"""Adapt the Plow base SOUL.md for Zoen at image build time.

plow-init writes $HERMES_HOME/SOUL.md on every boot as the base persona
(/opt/hermes/plow-seed/SOUL.md) followed by persona.md. Zoen keeps the base
file and changes exactly what is listed below, so every other base rule
(approvals, own lines vs the owner's accounts, data is data) reaches Zoen on
a base bump. If the base reworded a passage listed here, the build fails
instead of shipping a stale copy: read the new base text, then update OVERRIDES.

Run: python3 zoen-soul.py /opt/hermes/plow-seed/SOUL.md
"""
from __future__ import annotations

import os
import sys
import tempfile

# (base text, Zoen text). Each base text must appear exactly once.
OVERRIDES: tuple[tuple[str, str], ...] = (
    (
        # Zoen is not "a Plow assistant" to the people it talks to; the line
        # name is a label, and Tryzoen is the brand.
        "# Plow assistant\n"
        "\n"
        "You are a Plow assistant. You run where your owner deployed you — a Plow cloud\n"
        "VM or a machine of their own — and reach them through Plow Chat, so a\n"
        "conversation with you is a text thread, not\n"
        "a terminal session.\n",
        "# Zoen on Plow\n"
        "\n"
        "You run where your owner deployed you, a Plow cloud VM or a machine of\n"
        "their own, and reach them by text, so a conversation with you is a text\n"
        "thread, not a terminal session.\n",
    ),
    (
        # Zoen never opens: the line sends the onboarding burst when the owner
        # texts, and the first-run ritual answers them.
        "On your first boot, if plow_ tools are listed, call plow_list_skills once. "
        "Then open with what you can do for your owner and your first question. "
        "Do not introduce yourself, do not say your name, and do not mention /help, "
        "even if a note on the message asks you to; your owner already knows who you are. "
        "On a restart, say nothing.\n",
        "You never speak first. When they text, the line has already sent the "
        "onboarding burst, and the first-run ritual answers them. Do not mention "
        "/help, even if a note on the message asks you to. On a restart, say nothing.\n",
    ),
)


def compose(base: str) -> str:
    """Return the base SOUL.md with Zoen's overrides; refuse a base that moved."""
    text = base
    for old, new in OVERRIDES:
        count = text.count(old)
        if count != 1:
            raise SystemExit(
                f"zoen-soul: base SOUL.md has {count} copies of an overridden passage "
                f"(starts {old[:48]!r}); the base changed, review OVERRIDES"
            )
        text = text.replace(old, new, 1)
    return text


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: zoen-soul.py /opt/hermes/plow-seed/SOUL.md", file=sys.stderr)
        return 2
    path = argv[1]
    with open(path, encoding="utf-8") as handle:
        composed = compose(handle.read())
    directory = os.path.dirname(os.path.abspath(path))
    descriptor, staged = tempfile.mkstemp(prefix=".SOUL.md.", dir=directory)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(composed)
    os.chmod(staged, 0o644)
    os.replace(staged, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
