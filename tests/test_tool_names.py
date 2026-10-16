"""Every tool a prompt names is one the model can actually call.

A misspelled or retired tool name in a persona or skill is a silent failure:
the model reaches for it, the gateway has nothing by that name, and the turn
improvises. Founder Agent shipped `plow_list_chats`, which no plugin registers.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# hermes-plugin-plow at 7a5270e, the pin in base c692e80: every register_tool(name=...).
PLUGIN_TOOLS = {
    "plow_contacts",
    "plow_name_contact",
    "plow_offer_invite",
    "plow_request_payment",
    "plow_send_email",
    "plow_send_message",
    "plow_send_sequence",
    "plow_set_conversation_trusted",
}

# Latch on the owner's Mac, reached through the relay (Hermes may prefix them,
# e.g. mcp__plow__plow_run_command).
LATCH_TOOLS = {
    "plow_run_command",
    "plow_read_file",
    "plow_write_file",
    "plow_list_skills",
    "plow_read_skill",
    "plow_get_result",
    "plow_get_output",
    "plow_history",
    "plow_vault",
    "plow_browser",
    "plow_browser_open",
    "plow_browser_close",
    "plow_browser_request",
    "plow_device_status",
    "plow_run_applescript",
}

# zoen-face: zoen_connections is registered; zoen_imessage is plow_send_sequence renamed.
ZOEN_TOOLS = {"zoen_connections", "zoen_imessage"}

# The model never sees these names: quiet.py renames the sequence tool to zoen_imessage.
HIDDEN = {"plow_send_sequence"}


def _prompts():
    for folder in ("runtime", "skills"):
        yield from sorted((ROOT / folder).rglob("*.md"))


def test_every_named_tool_exists():
    known = PLUGIN_TOOLS | LATCH_TOOLS | ZOEN_TOOLS
    unknown = {}
    for path in _prompts():
        for name in re.findall(r"\b(?:plow|zoen)_[a-z_]+\b", path.read_text(encoding="utf-8")):
            if name not in known:
                unknown.setdefault(name, []).append(str(path.relative_to(ROOT)))
    assert not unknown, unknown


def test_prompts_use_the_renamed_tool():
    for path in _prompts():
        text = path.read_text(encoding="utf-8")
        for name in HIDDEN:
            assert name not in text, f"{path.relative_to(ROOT)} names {name}; the model calls zoen_imessage"


def test_the_renamed_tool_is_the_one_quiet_installs():
    quiet = (ROOT / "image/plugins/zoen-face/quiet.py").read_text()
    assert 'IMESSAGE = "zoen_imessage"' in quiet
    init = (ROOT / "image/plugins/zoen-face/__init__.py").read_text()
    assert 'name="zoen_connections"' in init
