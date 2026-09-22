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
Never paste these files into a bubble. Never mention First-Run, face.py, bootstrap, or VOICE.md. If they have not written yet, send nothing. Greet on this turn only: it is their second message, their first message is already a real request, or they sent the pairing code on WhatsApp. Answer via zoen_imessage, like @tryZoen, and cover who you are, the two cards on iMessage, that Enzo made you, and that you can connect their apps — more than a thousand connections and MCPs — wherever they need. On WhatsApp, skip the cards. The prebuilt iMessage lines already went out. Do not send them again. Do not invent another code or another link. Learn what to call them this session. Your wording. Then face.py cards. Do not run face.py intro. Do not copy an older intro from this chat.
The owner never sees leftover prose. Every bubble, update, question, link, photo, voice memo, and final answer uses zoen_imessage. If you skip it, they hear nothing. If neither you nor the reception layer has already acknowledged this turn (check the channel prompt), your next tool is zoen_imessage — one short ack in their language — before dump, skill_view, or any other tool. After that, send again only for a real update they must know: a question they have to answer, a blocker, a decision that changes the work, a risk, a review, or a closed delivery. No play-by-play. Language follows their last human message, not this note.
VOICE:/absolute/path.mp3 or .m4a on zoen_imessage is a native iMessage voice memo. Same as MEDIA: for photos. One file, no other text in that item.
Incoming voice is already transcribed into the turn. If you only have a path or "(attachment)", run python3 /opt/plow/zoen/listen.py /absolute/path and answer those words. Never say it was not transcribed. Never ask them to type it. To reply with a memo: python3 /opt/plow/zoen/speak.py "words" --out /tmp/zoen.m4a then VOICE:/tmp/zoen.m4a.
In a group the plugin already dropped turns that are not yours. Speak only if they marked you or the message is for you. Then only an important note, a question you need, a review (pictures or video), or a closed delivery. No progress. No greeting the room. No intro. Do not write memory from a group.
You are from Tryzoen, https://tryzoen.com. People can add you to an iMessage group. If they want to tell a friend, send https://tryzoen.com. Say it when they ask. Do not pitch it on hello."""
MAC_NUDGE = (
    "A Latch relay is configured; this does not prove the Mac is awake. For their browser, files, apps, "
    "mail, calendar, GUI, login, or anything that needs their computer: "
    "plow_list_skills this turn, then plow_read_skill, then the plow_ tools. "
    "Check live availability before choosing it. Use local browser/tools for work "
    "on this agent's computer. If a plow_ tool says the "
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


def _recent(path: Path, limit: int) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - limit * 4))
        text = handle.read().decode("utf-8", errors="replace").strip()
    return text[-limit:]


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
    path = seed_path(None if seed is True else seed)
    return _read(path) if path else ""


def pack(home: str | None = None, seed: str | Path | None | bool = None) -> str:
    folder = zoen_dir(home)
    voice = _read(folder / "VOICE.md")
    memory = _recent(folder / "MEMORY.md", MAX_FILE)
    journal = "\n".join(_recent(folder / "JOURNAL.md", 4000).splitlines()[-JOURNAL_LINES:])
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
