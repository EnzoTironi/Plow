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
from credits import (  # noqa: E402
    language as credits_language,
    mark_told,
    notice as credits_notice,
    recently_told,
    result_is_credits,
)
from lang import detect_language  # noqa: E402
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
ACK_MODEL = "openai/gpt-5.6-luna"
ACK_SYS = (
    "One iMessage ack. Same language as the user. Max two lines. "
    "No trailing period. No em dash. JSON only: {\"ack\":\"...\"}"
)
_CLOSER = {
    "thanks",
    "thank",
    "you",
    "thx",
    "tks",
    "ty",
    "valeu",
    "obrigado",
    "obrigada",
    "vlw",
    "tmj",
    "obg",
}
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


def latest_inbound(messages: Any) -> str:
    for item in message_rows(messages):
        if item.get("direction") == "inbound":
            return str(item.get("body") or "")
    return ""


def newest_rows(messages: Any) -> list[dict]:
    rows = message_rows(messages)
    if any(item.get("created_at") or item.get("sent_at") for item in rows):
        return sorted(
            rows,
            key=lambda item: str(item.get("created_at") or item.get("sent_at") or ""),
            reverse=True,
        )
    return list(rows)


def is_noise_row(item: dict) -> bool:
    if item.get("attachments"):
        return False
    body = str(item.get("body") or "")
    if not body.strip():
        return True
    lower = body.lower()
    return is_setup_text(body) or "gateway shutting down" in lower


def newest_is_inbound(messages: Any) -> bool:
    for item in newest_rows(messages):
        if is_noise_row(item):
            continue
        return item.get("direction") == "inbound"
    return False


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


def complete_http(
    system: str,
    user: str,
    *,
    http: Http,
    base: str,
    headers: dict[str, str] | None = None,
    max_tokens: int = 8,
    model: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if model:
        payload["model"] = model
    return http(
        "POST",
        f"{base}/v1/chat/completions",
        headers=headers,
        body=payload,
    )


def complete(
    system: str,
    user: str,
    *,
    http: Http,
    base: str,
    headers: dict[str, str] | None = None,
    max_tokens: int = 8,
    model: str | None = None,
) -> str | None:
    result = complete_http(
        system,
        user,
        http=http,
        base=base,
        headers=headers,
        max_tokens=max_tokens,
        model=model,
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
    prior: str | None = None,
    home: str | None = None,
) -> str:
    spoken = (text or "").strip()
    fallback = prior if prior is not None else voice_language(home)
    return detect_language(spoken, fallback)


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


def closer_only(text: str) -> bool:
    spoken = (text or "").strip()
    if not spoken:
        return False
    tokens = [tok.lower() for tok in re.findall(r"[^\W\d_]+", spoken, flags=re.UNICODE)]
    if not tokens:
        return True
    return all(tok in _CLOSER for tok in tokens)


def acked_path(home: str | None = None) -> Path | None:
    root = (home or os.environ.get("HERMES_HOME") or "").strip()
    if not root:
        return None
    return Path(root) / "zoen" / "acked"


def mark_acking(home: str | None = None) -> None:
    path = acked_path(home)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("acking\n", encoding="utf-8")


def _store_acked(home: str | None, body: str) -> None:
    path = acked_path(home)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _clear_acked(home: str | None) -> None:
    path = acked_path(home)
    if path is None or not path.is_file():
        return
    try:
        path.unlink()
    except OSError:
        return


def _ack_body(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        parsed = None
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                parsed = None
    if isinstance(parsed, dict) and parsed.get("ack"):
        text = str(parsed["ack"])
    lines = [line.strip() for line in text.splitlines() if line.strip()][:2]
    if not lines:
        return None
    cleaned: list[str] = []
    for line in lines:
        line = line.replace("—", ",").replace("–", ",")
        if line.endswith("."):
            line = line[:-1].rstrip()
        if line:
            cleaned.append(line)
    if not cleaned or any(len(line.splitlines()) > 1 for line in cleaned):
        return None
    return "\n".join(cleaned)


def send_ack(
    spoken: str,
    chat_uid: str,
    *,
    http: Http,
    home: str | None = None,
) -> None:
    mark_acking(home)
    try:
        base, headers = credentials()
    except SystemExit:
        return
    lang = pick_language(spoken, prior=voice_language(home), home=home)
    try:
        result = complete_http(
            ACK_SYS,
            spoken,
            http=http,
            base=base,
            headers=headers,
            max_tokens=40,
            model=ACK_MODEL,
        )
    except Exception:
        result = {"ok": False, "status": 0, "body": None, "error": "ack"}
    if result_is_credits(result):
        if recently_told(home):
            return
        body = credits_notice(lang or credits_language(home))
        sent = send_text(base, headers, chat_uid, body, http)
        if sent.get("ok"):
            mark_told(body, home)
            _store_acked(home, f"sent\n{body}\n")
        else:
            _clear_acked(home)
        return
    body = _ack_body(_completion_text(result.get("body")) if result.get("ok") else None)
    if not body:
        _clear_acked(home)
        return
    sent = send_text(base, headers, chat_uid, body, http)
    if sent.get("ok"):
        _store_acked(home, f"sent\n{body}\n")
    else:
        _clear_acked(home)


def maybe_ack(
    event: Any,
    *,
    http: Http | None = None,
    wait: bool = False,
    home: str | None = None,
) -> None:
    if event is None or getattr(event, "internal", False):
        return
    if is_plow_setup(event):
        return
    spoken = spoken_text(event) or str(getattr(event, "text", None) or "").strip()
    if not spoken or closer_only(spoken):
        return
    source = getattr(event, "source", None)
    chat_uid = str(getattr(source, "chat_id", None) or "").strip() if source else ""
    if not chat_uid.startswith("cht_"):
        return
    client = http or request

    def run() -> None:
        try:
            send_ack(spoken, chat_uid, http=client, home=home)
        except Exception:
            return

    task = threading.Thread(target=run, daemon=True, name="zoen-ack")
    task.start()
    if wait:
        task.join(timeout=8)


def group_transcript(
    event: Any,
    *,
    http: Http | None = None,
) -> str:
    client = http or request
    try:
        base, headers = credentials()
    except SystemExit:
        return ""
    source = getattr(event, "source", None)
    chat_uid = str(getattr(source, "chat_id", None) or "").strip() if source else ""
    if not chat_uid.startswith("cht_"):
        return ""
    listed = client(
        "GET",
        f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=12",
        headers=headers,
    )
    if not listed.get("ok"):
        return ""
    return format_transcript(listed.get("body"))


def group_cue(
    event: Any,
    spoken: str,
    *,
    http: Http | None = None,
) -> str:
    if not spoken:
        return "skip"
    name = str(getattr(event, "user_name", None) or "").strip().lower()
    if name in GOAL_NAMES:
        return "allow"
    if spoken.startswith("/"):
        return "allow"
    if mentioned(spoken):
        return "allow"
    lowered = spoken.strip().lower()
    if re.search(r"\b(almo[cç]ar|jantar|kk+|haha+|rsrs+|lol)\b", lowered):
        return "skip"
    if re.fullmatch(r"(oi|olá|opa|hey|hi)\W*", lowered):
        return "skip"
    transcript = group_transcript(event, http=http)
    lines = [line for line in transcript.splitlines() if line.strip()]
    if any(line.startswith("you:") for line in lines[-6:]):
        return "allow"
    return "tie"


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
    text = spoken_text(event)
    cue = group_cue(event, text, http=http)
    if cue == "allow":
        return {"action": "allow"}
    if cue == "skip":
        return {"action": "skip", "reason": "group silence"}
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


def voice_language(home: str | None = None) -> str | None:
    path = voice_path(home)
    if path is None or not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("language:"):
            token = line.split(":", 1)[1].strip().split()[0].lower()
            if len(token) >= 2 and token[:2].isalpha():
                return token[:2]
    return None


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
    if not force and is_setup_text(spoken):
        return {
            "ok": True,
            "skipped": "plow setup",
            "chat": chat_uid,
            "name": NAME,
            "language": "pt",
            "rename": renamed,
        }
    if not force and not spoken:
        return {
            "ok": True,
            "skipped": "waiting for inbound",
            "chat": chat_uid,
            "name": NAME,
            "language": "pt",
            "rename": renamed,
        }
    if not force and not (inbound or "").strip() and not newest_is_inbound(history):
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


def is_setup_text(text: str) -> bool:
    return (text or "").strip().lower().startswith(SETUP_PREFIX)


def is_plow_setup(event: Any) -> bool:
    spoken = spoken_text(event)
    if is_setup_text(spoken):
        return True
    if spoken:
        return False
    name = str(getattr(event, "user_name", None) or "").strip().lower()
    text = str(getattr(event, "text", None) or "")
    if is_setup_text(text):
        return True
    return name in SETUP_NAMES or name.startswith("plow setup")


def _call_intro(
    send: Callable[..., dict[str, Any]] | None,
    http: Http | None,
    put: Put | None,
    inbound: str | None = None,
) -> dict[str, Any]:
    if send is not None:
        return send(**({} if inbound is None else {"inbound": inbound}))
    kwargs: dict[str, Any] = {}
    if inbound is not None:
        kwargs["inbound"] = inbound
    if http is not None:
        kwargs["http"] = http
    if put is not None:
        kwargs["put"] = put
    return intro(**kwargs)


def _after_setup(
    *,
    voiced: bool | None,
    send: Callable[..., dict[str, Any]] | None,
    http: Http | None,
    put: Put | None,
) -> dict[str, str]:
    if send is not None or (voice_exists() if voiced is None else voiced):
        return {"action": "skip", "reason": "plow setup"}
    try:
        payload = _call_intro(send, http, put)
    except (Exception, SystemExit):
        return {"action": "skip", "reason": "plow setup"}
    if payload.get("ok") and payload.get("hello"):
        return {"action": "skip", "reason": "zoen intro"}
    return {"action": "skip", "reason": "plow setup"}


def greet_on_dispatch(
    event: Any = None,
    *,
    voiced: bool | None = None,
    send: Callable[..., dict[str, Any]] | None = None,
    http: Http | None = None,
    put: Put | None = None,
    wait_ack: bool = False,
    **_: Any,
) -> dict[str, str]:
    if getattr(event, "internal", False):
        return {"action": "allow"}
    if is_plow_setup(event):
        return _after_setup(voiced=voiced, send=send, http=http, put=put)
    if is_group(event):
        decision = group_on_dispatch(event, http=http)
        if decision.get("action") == "allow":
            maybe_ack(event, http=http, wait=wait_ack)
        return decision
    if voice_exists() if voiced is None else voiced:
        maybe_ack(event, http=http, wait=wait_ack)
        return {"action": "allow"}
    text = spoken_text(event) or str(getattr(event, "text", None) or "").strip()
    if not text or text.startswith("/"):
        maybe_ack(event, http=http, wait=wait_ack)
        return {"action": "allow"}
    try:
        payload = _call_intro(send, http, put, inbound=text)
    except (Exception, SystemExit):
        maybe_ack(event, http=http, wait=wait_ack)
        return {"action": "allow"}
    if payload.get("ok"):
        return {"action": "skip", "reason": "zoen intro"}
    maybe_ack(event, http=http, wait=wait_ack)
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
