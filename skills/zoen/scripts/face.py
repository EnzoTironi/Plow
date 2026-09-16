#!/usr/bin/env python3
"""Name the iMessage card Zoen and put the monster on it.

    face.py intro
    face.py rename
    face.py card --force

Intro is the first message: hello, then the card. Rename is install.
Auth: PLOW_API_BASE + PLOW_AGENT_TOKEN, optional PLOW_ACCOUNT_TOKEN
or ~/.config/plow/token.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import request  # noqa: E402

NAME = "Zoen"
CARD_NAME = "Zoen.vcf"
HELLO = {
    "en": (
        "hey, I'm Zoen\nyour little monster that makes your dreams come true",
        "save my card so you know it's me",
        "what's your dream?",
    ),
    "pt": (
        "oi, eu sou o Zoen\no monstrinho que faz seus sonhos acontecerem",
        "salva meu cartão pra você saber que sou eu",
        "qual é o seu sonho?",
    ),
}
HELLO_MARKERS = ("I'm Zoen", "eu sou o Zoen")
PT_MARKS = ("ã", "õ", "ç", "á", "é", "í", "ó", "ú", "ê", "ô", "à")
PT_WORDS = (
    " oi",
    "olá",
    "oie",
    "eae",
    "fala",
    "obrigad",
    "valeu",
    "tudo bem",
    "faz ",
    "meu ",
    "minha ",
    "pra ",
    "pro ",
    "não",
    "nao ",
)
Http = Callable[..., dict]
Put = Callable[[str, dict[str, str], bytes], dict]
Nap = Callable[[float], None]


def _out(payload: dict) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload.get("ok", True) else 1


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_credentials() -> None:
    here = Path(__file__).resolve()
    load_env_file(Path("plow-credentials"))
    load_env_file(here.parents[3] / "plow-credentials")


def account_token() -> str:
    if "PLOW_ACCOUNT_TOKEN" in os.environ:
        return os.environ["PLOW_ACCOUNT_TOKEN"].strip()
    path = Path.home() / ".config/plow/token"
    if path.is_file():
        return path.read_text().strip()
    return ""


def credentials() -> tuple[str, dict[str, str]]:
    load_credentials()
    base = (os.environ.get("PLOW_API_BASE") or "").strip().rstrip("/")
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not base or not token:
        raise SystemExit("face: set PLOW_API_BASE and PLOW_AGENT_TOKEN")
    return base, {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def photo_path() -> Path:
    env = (os.environ.get("ZOEN_CARD_PHOTO") or "").strip()
    if env:
        path = Path(env)
        if not path.is_file():
            raise SystemExit(f"face: photo not found: {path}")
        return path
    here = Path(__file__).resolve()
    for candidate in (
        Path("/usr/share/doc/zoen/zoen-card.jpg"),
        here.parents[3] / "docs" / "zoen-card.jpg",
        here.parent / "zoen-card.jpg",
    ):
        if candidate.is_file():
            return candidate
    raise SystemExit("face: no zoen-card.jpg")


def fold_line(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks: list[bytes] = []
    while raw:
        take = 75 if not chunks else 74
        piece = raw[:take]
        while piece.endswith(b"\n") or (len(piece) == take and (piece[-1] & 0xC0) == 0x80):
            piece = piece[:-1]
        if not piece:
            piece = raw[:1]
        chunks.append(piece)
        raw = raw[len(piece) :]
    first, *rest = (chunk.decode("utf-8") for chunk in chunks)
    return "\r\n ".join([first, *rest])


def vcard(name: str, tel: str, jpeg: bytes) -> bytes:
    photo = base64.b64encode(jpeg).decode("ascii")
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{name};;;;",
        f"FN:{name}",
        f"TEL;TYPE=CELL,VOICE,pref:{tel}",
        fold_line(f"PHOTO;ENCODING=b;TYPE=JPEG:{photo}"),
        "END:VCARD",
        "",
    ]
    return "\r\n".join(lines).encode("utf-8")


def home_chat(me: dict, explicit: str | None = None) -> str:
    value = (explicit or os.environ.get("PLOW_HOME_CHANNEL") or "").strip()
    if value.startswith("cht_"):
        return value
    for chat in me.get("chats") or []:
        if not isinstance(chat, dict) or chat.get("status") != "active":
            continue
        uid = str(chat.get("uid") or "")
        members = [
            part
            for part in chat.get("participants") or []
            if isinstance(part, dict) and part.get("type") == "member"
        ]
        if uid.startswith("cht_") and len(members) == 1 and members[0].get("role") == "owner":
            return uid
    raise SystemExit("face: no home chat")


def message_rows(messages: Any) -> list[dict]:
    rows = messages.get("data") if isinstance(messages, dict) else None
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def already_sent(messages: Any, filename: str = CARD_NAME) -> bool:
    for item in message_rows(messages):
        if item.get("direction") != "outbound":
            continue
        for att in item.get("attachments") or []:
            if isinstance(att, dict) and att.get("filename") == filename:
                return True
    return False


def hello_sent(messages: Any) -> bool:
    for item in message_rows(messages):
        if item.get("direction") != "outbound":
            continue
        body = str(item.get("body") or "")
        if any(marker in body for marker in HELLO_MARKERS):
            return True
    return False


def already_talked(messages: Any) -> bool:
    for item in message_rows(messages):
        if item.get("direction") != "outbound":
            continue
        if str(item.get("body") or "").strip():
            return True
    return False


def latest_inbound(messages: Any) -> str:
    for item in message_rows(messages):
        if item.get("direction") == "inbound":
            return str(item.get("body") or "")
    return ""


def pick_language(text: str) -> str:
    if not (text or "").strip():
        return "pt"
    lower = f" {text.lower()} "
    if any(mark in text.lower() for mark in PT_MARKS):
        return "pt"
    if any(word in lower for word in PT_WORDS):
        return "pt"
    return "en"


def put_bytes(url: str, headers: dict[str, str], data: bytes) -> dict:
    req = Request(url, data=data, method="PUT", headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            resp.read()
            return {"ok": True, "status": resp.status, "error": None}
    except HTTPError as exc:
        exc.read()
        return {"ok": False, "status": exc.code, "error": str(exc.reason)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def load_me(http: Http) -> tuple[str, dict[str, str], dict]:
    base, headers = credentials()
    me = http("GET", f"{base}/v1/agents/me", headers=headers)
    body = me.get("body") if me.get("ok") else None
    if not isinstance(body, dict):
        raise SystemExit(f"face: could not read identity: {me.get('error') or me.get('status')}")
    return base, headers, body


def rename_agent(base: str, me: dict, http: Http) -> dict[str, Any] | None:
    agent = me.get("agent") if isinstance(me.get("agent"), dict) else {}
    uid = str(agent.get("uid") or "")
    token = account_token()
    if not token or not uid:
        return None
    result = http(
        "PATCH",
        f"{base}/v1/agents/{quote(uid, safe='')}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        body={"name": NAME},
    )
    renamed = {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "error": result.get("error"),
        "name": NAME,
    }
    if not result.get("ok"):
        raise SystemExit(f"face: rename failed: {result.get('error') or result.get('status')}")
    return renamed


def send_card(
    base: str,
    headers: dict[str, str],
    chat_uid: str,
    tel: str,
    http: Http,
    put: Put,
) -> dict[str, Any]:
    jpeg = photo_path().read_bytes()
    card = vcard(NAME, tel, jpeg)
    declared = http(
        "POST",
        f"{base}/v1/chats/{quote(chat_uid)}/attachments",
        headers=headers,
        body={
            "filename": CARD_NAME,
            "content_type": "text/vcard",
            "size_bytes": len(card),
        },
    )
    upload = declared.get("body") if declared.get("ok") else None
    if not isinstance(upload, dict) or not upload.get("uid") or not upload.get("upload_url"):
        return {
            "ok": False,
            "error": declared.get("error") or "could not declare the card",
            "status": declared.get("status"),
        }
    stored = put(str(upload["upload_url"]), dict(upload.get("upload_headers") or {}), card)
    if not stored.get("ok"):
        return {
            "ok": False,
            "error": stored.get("error") or "card upload failed",
            "status": stored.get("status"),
        }
    sent = http(
        "POST",
        f"{base}/v1/chats/{quote(chat_uid)}/messages",
        headers=headers,
        body={"body": "", "attachment_uids": [upload["uid"]]},
    )
    return {
        "ok": bool(sent.get("ok")),
        "status": sent.get("status"),
        "error": sent.get("error"),
        "attachment": upload.get("uid"),
    }


def send_text(
    base: str,
    headers: dict[str, str],
    chat_uid: str,
    body: str,
    http: Http,
) -> dict[str, Any]:
    sent = http(
        "POST",
        f"{base}/v1/chats/{quote(chat_uid)}/messages",
        headers=headers,
        body={"body": body, "format": "none"},
    )
    return {
        "ok": bool(sent.get("ok")),
        "status": sent.get("status"),
        "error": sent.get("error"),
    }


def apply(
    force: bool = False,
    chat: str | None = None,
    http: Http = request,
    put: Put = put_bytes,
) -> dict[str, Any]:
    base, headers, me = load_me(http)
    line = me.get("line") if isinstance(me.get("line"), dict) else {}
    tel = str(line.get("provider_key") or "").strip()
    if not tel:
        raise SystemExit("face: line has no number")
    renamed = rename_agent(base, me, http)
    chat_uid = home_chat(me, chat)
    listed = http(
        "GET",
        f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=20",
        headers=headers,
    )
    if listed.get("ok") and already_sent(listed.get("body")) and not force:
        return {
            "ok": True,
            "skipped": "already sent",
            "chat": chat_uid,
            "name": NAME,
            "rename": renamed,
        }
    sent = send_card(base, headers, chat_uid, tel, http, put)
    sent.update({"chat": chat_uid, "name": NAME, "rename": renamed})
    return sent


def intro(
    force: bool = False,
    chat: str | None = None,
    http: Http = request,
    put: Put = put_bytes,
    nap: Nap = time.sleep,
) -> dict[str, Any]:
    base, headers, me = load_me(http)
    line = me.get("line") if isinstance(me.get("line"), dict) else {}
    tel = str(line.get("provider_key") or "").strip()
    if not tel:
        raise SystemExit("face: line has no number")
    renamed = rename_agent(base, me, http)
    chat_uid = home_chat(me, chat)
    listed = http(
        "GET",
        f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=20",
        headers=headers,
    )
    history = listed.get("body") if listed.get("ok") else {}
    lang = pick_language(latest_inbound(history))
    bubbles = list(HELLO[lang])
    want_hello = force or not (hello_sent(history) or already_talked(history))
    want_card = force or not already_sent(history)
    if not want_hello and not want_card:
        return {
            "ok": True,
            "skipped": "already sent",
            "chat": chat_uid,
            "name": NAME,
            "language": lang,
            "rename": renamed,
        }
    sent_hello: list[str] = []
    pace = 0

    def wait() -> None:
        nonlocal pace
        nap(1.75 if pace % 2 == 0 else 2.0)
        pace += 1

    def fail(result: dict[str, Any]) -> dict[str, Any]:
        result.update({
            "chat": chat_uid,
            "name": NAME,
            "hello": sent_hello,
            "rename": renamed,
        })
        return result

    def say(bubble: str) -> dict[str, Any] | None:
        if sent_hello:
            wait()
        result = send_text(base, headers, chat_uid, bubble, http)
        if not result.get("ok"):
            return fail(result)
        sent_hello.append(bubble)
        return None

    opening, ask = bubbles[:-1], bubbles[-1]
    if want_hello:
        for bubble in opening:
            failed = say(bubble)
            if failed:
                return failed
    attachment = None
    if want_card:
        if sent_hello:
            wait()
        result = send_card(base, headers, chat_uid, tel, http, put)
        if not result.get("ok"):
            return fail(result)
        attachment = result.get("attachment")
    if want_hello:
        failed = say(ask)
        if failed:
            return failed
    return {
        "ok": True,
        "chat": chat_uid,
        "name": NAME,
        "language": lang,
        "hello": sent_hello,
        "attachment": attachment,
        "rename": renamed,
    }


def rename(
    chat: str | None = None,
    http: Http = request,
) -> dict[str, Any]:
    base, _headers, me = load_me(http)
    renamed = rename_agent(base, me, http)
    return {"ok": True, "name": NAME, "rename": renamed, "chat": home_chat(me, chat)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="intro",
        choices=("intro", "rename", "card"),
        help="intro is the first message, rename is install, card is the vCard only",
    )
    parser.add_argument("--force", action="store_true", help="send even if one already went")
    parser.add_argument("--chat", help="cht_... (default home DM)")
    return parser


def main(
    argv: list[str] | None = None,
    http: Http = request,
    put: Put = put_bytes,
    nap: Nap = time.sleep,
) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "rename":
        return _out(rename(chat=args.chat, http=http))
    if args.mode == "card":
        return _out(apply(force=args.force, chat=args.chat, http=http, put=put))
    return _out(intro(force=args.force, chat=args.chat, http=http, put=put, nap=nap))


if __name__ == "__main__":
    raise SystemExit(main())
