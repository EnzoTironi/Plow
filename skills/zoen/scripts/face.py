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
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory import remember  # noqa: E402
from net import request  # noqa: E402

NAME = "Zoen"
CARD_NAME = "Zoen.vcf"
HELLO = {
    "en": (
        "hey, I'm Zoen, your little monster that makes your dreams come true",
        "save my card so you know it's me",
        "what's your dream?",
    ),
    "pt": (
        "oi, eu sou o Zoen, o monstrinho que faz seus sonhos acontecerem",
        "salva meu cartão pra você saber que sou eu",
        "qual é o seu sonho?",
    ),
}
SETUP_NAMES = {"plow setup"}
SETUP_PREFIX = "plow, not your owner"
HELLO_MARKERS = ("I'm Zoen", "eu sou o Zoen")
CARD_AFTER = 2
JUDGE = (
    "What language is this chat message written in? "
    "Reply with one token only: pt if Portuguese including Brazilian slang, "
    "en if it is entirely English, otherwise the ISO 639-1 code (es, fr, de, ja)."
)
DIRECTED = (
    "Zoen is a software-factory agent in this iMessage group. "
    "People may also use another contact name for the same number. "
    "Is the latest message for Zoen to act on or answer? "
    "Reply with one token only: yes or no. "
    "yes if they name Zoen, reply to Zoen, assign Zoen work, ask Zoen, "
    "or continue a task Zoen was just doing with nobody else addressed since. "
    "no if they talk to each other, greet the room, name someone else, "
    "or say something merely interesting. Unsure: no."
)
JUDGE_MODEL = "anthropic/claude-sonnet-5"
MENTION = re.compile(r"(?<!\w)@?zoen(?!\w)", re.IGNORECASE)
GOAL_NAMES = {"goal check"}
PEEK = (
    (["id", "-F"], "full name"),
    (["id", "-un"], "mac username"),
    (["git", "config", "--global", "user.email"], "email"),
)
RENDER = (
    "Rewrite these three iMessage bubbles in the same language as the user. "
    "Keep the meaning. Max two lines each. No trailing period. "
    "JSON only: {\"hello\":[\"...\",\"...\",\"...\"]}"
)
Http = Callable[..., dict]
Put = Callable[[str, dict[str, str], bytes], dict]


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
    xdg = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
    candidates = []
    if xdg:
        candidates.append(Path(xdg) / "plow" / "token")
    candidates.append(Path.home() / ".config" / "plow" / "token")
    for path in candidates:
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


def newest_row(messages: Any) -> dict | None:
    rows = message_rows(messages)
    if not rows:
        return None
    if any(item.get("created_at") or item.get("sent_at") for item in rows):
        return max(
            rows,
            key=lambda item: str(item.get("created_at") or item.get("sent_at") or ""),
        )
    return rows[0]


def newest_is_inbound(messages: Any) -> bool:
    row = newest_row(messages)
    return bool(row and row.get("direction") == "inbound")


def latest_inbound(messages: Any) -> str:
    for item in message_rows(messages):
        if item.get("direction") == "inbound":
            return str(item.get("body") or "")
    return ""


def _completion_text(body: Any) -> str:
    if not isinstance(body, dict):
        return str(body or "")
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message")
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"])
        if first.get("text"):
            return str(first["text"])
    return str(body.get("output") or "")


def _judge_model() -> str:
    return (
        (os.environ.get("ZOEN_LANG_MODEL") or "").strip()
        or (os.environ.get("HERMES_MODEL") or "").strip()
        or JUDGE_MODEL
    )


def complete(
    system: str,
    user: str,
    *,
    http: Http,
    base: str,
    headers: dict[str, str] | None = None,
    max_tokens: int = 8,
) -> str | None:
    result = http(
        "POST",
        f"{base}/v1/chat/completions",
        headers=headers,
        body={
            "model": _judge_model(),
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )
    if not result.get("ok"):
        return None
    return _completion_text(result.get("body"))


def normalize_lang(token: str) -> str:
    word = token.strip().lower().replace("-", " ").split()[0] if token else ""
    if word.startswith("en"):
        return "en"
    if word.startswith("pt") or word in {"por", "portuguese"}:
        return "pt"
    if len(word) == 2 and word.isalpha():
        return word
    return "pt"


def pick_language(
    text: str,
    *,
    http: Http | None = None,
    base: str = "",
    headers: dict[str, str] | None = None,
) -> str:
    spoken = (text or "").strip()
    if not spoken:
        return "pt"
    if http is None or not base:
        return "pt"
    token = complete(JUDGE, spoken, http=http, base=base, headers=headers)
    if not token:
        return "pt"
    return normalize_lang(token)


def render_hello(
    text: str,
    *,
    http: Http,
    base: str,
    headers: dict[str, str] | None,
) -> list[str]:
    source = "\n---\n".join(HELLO["en"])
    result = http(
        "POST",
        f"{base}/v1/chat/completions",
        headers=headers,
        body={
            "model": _judge_model(),
            "temperature": 0,
            "max_tokens": 160,
            "messages": [
                {"role": "system", "content": RENDER},
                {"role": "user", "content": f"{text}\n---\n{source}"},
            ],
        },
    )
    if not result.get("ok"):
        return list(HELLO["en"])
    raw = _completion_text(result.get("body")).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return list(HELLO["en"])
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return list(HELLO["en"])
    bubbles = parsed.get("hello") if isinstance(parsed, dict) else parsed
    if not isinstance(bubbles, list) or len(bubbles) != 3:
        return list(HELLO["en"])
    out = [str(item).strip() for item in bubbles]
    if any(not item or len(item.splitlines()) > 2 for item in out):
        return list(HELLO["en"])
    return out


def hello_for(
    lang: str,
    spoken: str,
    *,
    http: Http | None = None,
    base: str = "",
    headers: dict[str, str] | None = None,
) -> list[str]:
    if lang in HELLO:
        return list(HELLO[lang])
    if http is None or not base:
        return list(HELLO["en"])
    return render_hello(spoken, http=http, base=base, headers=headers)


def is_group(event: Any) -> bool:
    source = getattr(event, "source", None)
    kind = getattr(source, "chat_type", None) if source is not None else None
    return bool(kind) and kind != "dm"


def spoken_text(event: Any) -> str:
    recall = str(getattr(event, "recall_text", None) or "").strip()
    if recall:
        return recall
    return str(getattr(event, "text", None) or "").strip()


def mentioned(text: str) -> bool:
    return bool(MENTION.search(text or ""))


def normalize_yes(token: str) -> bool:
    word = token.strip().lower().replace("-", " ").split()[0] if token else ""
    return word in {"yes", "y", "sim"}


def format_transcript(messages: Any, cap: int = 8) -> str:
    rows = message_rows(messages)
    if any(item.get("created_at") or item.get("sent_at") for item in rows):
        rows = sorted(
            rows,
            key=lambda item: str(item.get("created_at") or item.get("sent_at") or ""),
        )
    else:
        rows = list(reversed(rows))
    lines: list[str] = []
    for item in rows[-cap:]:
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        who = "you" if item.get("direction") == "outbound" else "them"
        lines.append(f"{who}: {body}")
    return "\n".join(lines)


def directed_at_zoen(
    event: Any,
    spoken: str,
    *,
    http: Http | None = None,
) -> bool:
    if not spoken:
        return False
    client = http or request
    try:
        base, headers = credentials()
    except SystemExit:
        return False
    source = getattr(event, "source", None)
    chat_uid = str(getattr(source, "chat_id", None) or "").strip() if source else ""
    transcript = ""
    if chat_uid.startswith("cht_"):
        listed = client(
            "GET",
            f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=12",
            headers=headers,
        )
        if listed.get("ok"):
            transcript = format_transcript(listed.get("body"))
    user = f"{transcript}\n\nLatest:\n{spoken}" if transcript else spoken
    try:
        token = complete(
            DIRECTED, user, http=client, base=base, headers=headers, max_tokens=4
        )
    except Exception:
        return False
    if not token:
        return False
    return normalize_yes(token)


def latch_call(
    name: str,
    arguments: dict[str, Any] | None = None,
    timeout: int = 12,
) -> dict | None:
    url = (os.environ.get("PLOW_MCP_URL") or "").strip()
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not url or not token:
        return None
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    ).encode()
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return None
    if raw.lstrip().startswith("event:") or "\ndata:" in raw or raw.startswith("data:"):
        raw = "\n".join(
            line[5:].strip() for line in raw.splitlines() if line.startswith("data:")
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    result = parsed.get("result") if isinstance(parsed, dict) else None
    if not isinstance(result, dict) or result.get("isError"):
        return None
    payload = result.get("structuredContent")
    if payload is None:
        texts = [
            item.get("text")
            for item in (result.get("content") or [])
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if not texts:
            return None
        try:
            payload = json.loads(texts[0])
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    if payload.get("status", "completed") != "completed":
        return None
    return payload


def fact_from_output(label: str, output: str) -> str | None:
    value = (output or "").strip().splitlines()
    value = value[0].strip() if value else ""
    if not value or len(value) > 120 or value.lower() in {"none", "null"}:
        return None
    return f"{label}: {value}"


def facts_from_latch() -> list[str]:
    facts: list[str] = []
    for argv, label in PEEK:
        payload = latch_call("plow_run_command", {"argv": argv})
        if not payload or payload.get("exit_code") not in (0, None):
            continue
        fact = fact_from_output(label, str(payload.get("output") or ""))
        if fact:
            facts.append(fact)
    return facts


def peek_owner(
    *,
    home: str | None = None,
    latch: Callable[[], list[str]] | None = None,
    remember_facts: Callable[..., Any] | None = None,
    wait: bool = False,
) -> None:
    def run() -> None:
        try:
            facts = (latch or facts_from_latch)()
            if facts:
                (remember_facts or remember)(facts, home=home)
        except Exception:
            return

    if wait:
        run()
        return
    threading.Thread(target=run, daemon=True, name="zoen-latch-peek").start()


def group_on_dispatch(
    event: Any,
    *,
    http: Http | None = None,
) -> dict[str, str]:
    name = str(getattr(event, "user_name", None) or "").strip().lower()
    if name in GOAL_NAMES:
        return {"action": "allow"}
    text = spoken_text(event)
    if text.startswith("/"):
        return {"action": "allow"}
    if mentioned(text):
        return {"action": "allow"}
    try:
        if directed_at_zoen(event, text, http=http):
            return {"action": "allow"}
    except Exception:
        return {"action": "skip", "reason": "group silence"}
    return {"action": "skip", "reason": "group silence"}


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
    return renamed


def upload_card(
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
    return {"ok": True, "uid": upload["uid"], "status": stored.get("status")}


def attach_card(
    base: str,
    headers: dict[str, str],
    chat_uid: str,
    uid: str,
    http: Http,
) -> dict[str, Any]:
    sent = http(
        "POST",
        f"{base}/v1/chats/{quote(chat_uid)}/messages",
        headers=headers,
        body={"body": "", "attachment_uids": [uid]},
    )
    return {
        "ok": bool(sent.get("ok")),
        "status": sent.get("status"),
        "error": sent.get("error"),
        "attachment": uid,
    }


def send_card(
    base: str,
    headers: dict[str, str],
    chat_uid: str,
    tel: str,
    http: Http,
    put: Put,
) -> dict[str, Any]:
    uploaded = upload_card(base, headers, chat_uid, tel, http, put)
    if not uploaded.get("ok"):
        return uploaded
    return attach_card(base, headers, chat_uid, str(uploaded["uid"]), http)


def voice_path(home: str | None = None) -> Path | None:
    root = (home or os.environ.get("HERMES_HOME") or "").strip()
    if not root:
        return None
    return Path(root) / "zoen" / "VOICE.md"


def voice_exists(home: str | None = None) -> bool:
    path = voice_path(home)
    return bool(path and path.is_file() and path.read_text(encoding="utf-8").strip())


def stamp_voice(lang: str, home: str | None = None) -> str | None:
    path = voice_path(home)
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8").strip():
        return "exists"
    path.write_text(f"language: {lang}\n", encoding="utf-8")
    return "wrote"


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
    inbound: str | None = None,
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
    history = listed.get("body") if listed.get("ok") else {}
    spoken = (inbound or "").strip() or latest_inbound(history)
    if not force and not newest_is_inbound(history) and not (inbound or "").strip():
        return {
            "ok": True,
            "skipped": "waiting for inbound",
            "chat": chat_uid,
            "name": NAME,
            "language": "pt",
            "rename": renamed,
        }
    voiced = voice_exists()
    want_hello = force or not (hello_sent(history) and voiced)
    want_card = force or not (already_sent(history) and voiced)
    if not want_hello and not want_card:
        voice = stamp_voice(pick_language(spoken))
        return {
            "ok": True,
            "skipped": "already sent",
            "chat": chat_uid,
            "name": NAME,
            "language": pick_language(spoken),
            "rename": renamed,
            "voice": voice,
        }
    sent_hello: list[str] = []

    def fail(result: dict[str, Any]) -> dict[str, Any]:
        result.update({
            "chat": chat_uid,
            "name": NAME,
            "hello": sent_hello,
            "rename": renamed,
        })
        return result

    def say(bubble: str) -> dict[str, Any] | None:
        result = send_text(base, headers, chat_uid, bubble, http)
        if not result.get("ok"):
            return fail(result)
        sent_hello.append(bubble)
        return None

    def judge() -> str:
        try:
            return pick_language(spoken, http=http, base=base, headers=headers)
        except Exception:
            return "pt"

    def pack() -> dict[str, Any]:
        return upload_card(base, headers, chat_uid, tel, http, put)

    peek_owner(home=os.environ.get("HERMES_HOME"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        lang_job = pool.submit(judge)
        card_job = pool.submit(pack) if want_card else None
        lang = lang_job.result()
        bubbles = hello_for(lang, spoken, http=http, base=base, headers=headers)
        before, after = bubbles[:CARD_AFTER], bubbles[CARD_AFTER:]
        if want_hello:
            for bubble in before:
                failed = say(bubble)
                if failed:
                    return failed
        attachment = None
        if want_card:
            assert card_job is not None
            try:
                uploaded = card_job.result()
            except Exception as exc:
                return fail({"ok": False, "error": str(exc), "status": 0})
            if not uploaded.get("ok"):
                return fail(uploaded)
            posted = attach_card(base, headers, chat_uid, str(uploaded["uid"]), http)
            if not posted.get("ok"):
                return fail(posted)
            attachment = posted.get("attachment")
        if want_hello:
            for bubble in after:
                failed = say(bubble)
                if failed:
                    return failed
    voice = stamp_voice(lang)
    return {
        "ok": True,
        "chat": chat_uid,
        "name": NAME,
        "language": lang,
        "hello": sent_hello,
        "attachment": attachment,
        "rename": renamed,
        "voice": voice,
    }


def is_plow_setup(event: Any) -> bool:
    name = str(getattr(event, "user_name", None) or "").strip().lower()
    if name in SETUP_NAMES or name.startswith("plow setup"):
        return True
    text = str(getattr(event, "text", None) or "").strip().lower()
    return text.startswith(SETUP_PREFIX)


def greet_on_dispatch(
    event: Any = None,
    *,
    voiced: bool | None = None,
    send: Callable[..., dict[str, Any]] | None = None,
    http: Http | None = None,
    **_: Any,
) -> dict[str, str]:
    if getattr(event, "internal", False):
        return {"action": "allow"}
    if is_plow_setup(event):
        return {"action": "skip", "reason": "plow setup"}
    if is_group(event):
        return group_on_dispatch(event, http=http)
    if voice_exists() if voiced is None else voiced:
        return {"action": "allow"}
    text = str(getattr(event, "text", None) or "").strip()
    if not text or text.startswith("/"):
        return {"action": "allow"}
    run = intro if send is None else send
    try:
        payload = run(inbound=text)
    except (Exception, SystemExit):
        return {"action": "allow"}
    if payload.get("ok"):
        return {"action": "skip", "reason": "zoen intro"}
    return {"action": "allow"}


def rename(
    http: Http = request,
) -> dict[str, Any]:
    base, _headers, me = load_me(http)
    renamed = rename_agent(base, me, http)
    if renamed is None:
        return {"ok": False, "error": "no account token", "name": NAME}
    if not renamed.get("ok"):
        return {
            "ok": False,
            "error": renamed.get("error") or "rename failed",
            "name": NAME,
            "rename": renamed,
        }
    return {"ok": True, "name": NAME, "rename": renamed}


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
) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "rename":
        return _out(rename(http=http))
    if args.mode == "card":
        return _out(apply(force=args.force, chat=args.chat, http=http, put=put))
    return _out(intro(force=args.force, chat=args.chat, http=http, put=put))


if __name__ == "__main__":
    raise SystemExit(main())
