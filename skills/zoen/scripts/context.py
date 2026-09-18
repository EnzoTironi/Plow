#!/usr/bin/env python3
"""Pack the owner's zoen files the way a turn needs them.

    context.py dump

Prints a First-Run Ritual when VOICE.md is still missing, then `<info>`
(voice + memory + recent journal) then `<NOW.md>`. Missing files are
omitted, not invented. Bones only: no voice.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

NOW_OPEN = "<NOW.md Always keep this up to date; keep under 10 lines>"
NOW_CLOSE = "</NOW.md>"
INFO_OPEN = "<info>"
INFO_CLOSE = "</info>"
RITUAL_HEAD = "# First-Run Ritual"
REMINDER_OPEN = "<system_reminder>"
REMINDER_CLOSE = "</system_reminder>"
IMAGE_SEED = Path("/opt/hermes/plow-seed/bootstrap.md")
MAX_FILE = 6000
NOW_LINES = 10
JOURNAL_LINES = 12
REMINDER = """Stay present in this conversation.
When something concrete lands, remember it the same turn, in the background: names, dates, plans, decisions, preferences, felt moments. Corrections are the highest priority. Write naturally. Do not categorize. Do not batch. Do not wait. Skip small talk and hypotheticals.
python3 /opt/plow/zoen/memory.py remember "the fact"
Several facts: one call, several arguments.
Never tell them you saved a memory. Never "anotei", "salvei", "vou lembrar", "noted that", "I'll remember that". No bubble about remembering. Just remember, then keep talking.
Only if they asked you directly to save it ("salva isso", "lembra que", "anota", "remember this"): one short ack in their language, then remember. That answers the ask. Do not describe the save. Do not volunteer this when they did not ask.

The pack above is incomplete by design. It surfaces patterns, not the specifics. If you catch yourself reaching for "I think", "maybe", "if I remember", "last time", "didn't we": recall before you ask or guess. Recall is also silent. Never narrate it.
python3 /opt/plow/zoen/memory.py recall "who is Enzo"
Call recall whenever they mention someone, a repo, a decision, or prior work you should already know. Guessing costs trust. Searching costs nothing.
Never paste these files into a bubble. Never mention First-Run, face.py, bootstrap, or VOICE.md. If they have not written yet, send nothing. The first bubble is only what intro sends.
As soon as you understand their ask, plow_send_sequence one short ack in their language, then work. You send that first ack. Do not wait for a plugin. Do not send again until a review or a closed delivery. No progress narration. Any language they use, you use.
VOICE:/absolute/path.mp3 or .m4a on plow_send_sequence is a native iMessage voice memo. Same as MEDIA: for photos. One file, no other text in that item.
In a group the plugin already dropped turns that are not yours. Speak only if they marked you or the message is for you. Then only an important note, a question you need, a review (pictures or video), or a closed delivery. No progress. No greeting the room. No intro. Do not write memory from a group."""
MAC_NUDGE = (
    "The owner's Mac is connected. For automations, their browser, files, apps, "
    "mail, calendar, GUI, login, or anything that needs their computer: "
    "plow_list_skills this turn, then plow_read_skill, then the plow_ tools. "
    "Do not ask them to click, type, or install. Do not do that work in this "
    "container. Git, tests, and the PR stay in here. If a plow_ tool says the "
    "Mac is asleep, tell them once to open Latch."
)


def zoen_dir(home: str | None = None) -> Path:
    root = (home or os.environ.get("HERMES_HOME") or "").strip() or "/var/lib/hermes"
    return Path(root) / "zoen"


def seed_path(seed: str | Path | None | bool = None) -> Path | None:
    if seed is False:
        return None
    if seed and seed is not True:
        return Path(seed)
    env = (os.environ.get("ZOEN_BOOTSTRAP_SEED") or "").strip()
    if env:
        return Path(env)
    if IMAGE_SEED.is_file():
        return IMAGE_SEED
    here = Path(__file__).resolve()
    for root in here.parents:
        candidate = root / "runtime" / "bootstrap.md"
        if candidate.is_file():
            return candidate
    return IMAGE_SEED


def _read(path: Path, limit: int = MAX_FILE) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def _escape(text: str, close: str) -> str:
    return text.replace(close, close.replace("<", "&lt;").replace(">", "&gt;"))


def _heading(title: str, body: str) -> str:
    if not body:
        return ""
    return f"## {title}\n\n{body}"


def mac_connected() -> bool:
    return bool((os.environ.get("PLOW_MCP_URL") or "").strip())


def reminder_body() -> str:
    if not mac_connected():
        return REMINDER
    return f"{REMINDER}\n{MAC_NUDGE}"


def first_run(home: str | None = None, seed: str | Path | None | bool = None) -> str:
    folder = zoen_dir(home)
    if _read(folder / "VOICE.md"):
        return ""
    living = _read(folder / "BOOTSTRAP.md")
    if living:
        return living
    path = seed_path(None if seed is True else seed)
    return _read(path) if path else ""


def pack(home: str | None = None, seed: str | Path | None | bool = None) -> str:
    folder = zoen_dir(home)
    voice = _read(folder / "VOICE.md")
    memory = _read(folder / "MEMORY.md")
    journal = _read(folder / "JOURNAL.md", limit=4000)
    if journal:
        lines = journal.splitlines()
        journal = "\n".join(lines[-JOURNAL_LINES:]).strip()
    now = _read(folder / "NOW.md", limit=2000)
    if now:
        now = "\n".join(now.splitlines()[:NOW_LINES]).strip()

    info_parts = [
        _heading("Voice Profile", voice),
        _heading("Essentials", memory),
        _heading("Recent", journal),
    ]
    info_body = "\n\n".join(part for part in info_parts if part)
    blocks: list[str] = []
    ritual = first_run(home, seed)
    if ritual:
        blocks.append(f"{RITUAL_HEAD}\n\n{ritual}")
    if info_body:
        blocks.append(f"{INFO_OPEN}\n{_escape(info_body, INFO_CLOSE)}\n{INFO_CLOSE}")
    if now:
        blocks.append(f"{NOW_OPEN}\n{_escape(now, NOW_CLOSE)}\n{NOW_CLOSE}")
    blocks.append(f"{REMINDER_OPEN}\n{reminder_body()}\n{REMINDER_CLOSE}")
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if args and args[0] not in ("dump",):
        print("context: dump", file=sys.stderr)
        return 2
    packed = pack()
    if packed:
        sys.stdout.write(packed + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
