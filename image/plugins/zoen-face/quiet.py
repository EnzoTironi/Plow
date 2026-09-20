"""Owner iMessage goes through zoen_imessage; leftover send is dropped."""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import re
import sys
import urllib.request
from contextlib import nullcontext
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

_SCRIPTS = Path("/opt/plow/zoen")
_REPO_SCRIPTS = Path(__file__).resolve().parents[3] / "skills/zoen/scripts"
for _path in (_SCRIPTS, _REPO_SCRIPTS):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from credits import (  # noqa: E402
    language as credits_language,
    looks_like as credits_looks_like,
    mark_told,
    notice as credits_notice,
    recently_told,
)

log = logging.getLogger("zoen-face")
_RETIRED_HELLO = (
    "a gente te ajuda",
    "we'll help.",
    "+55 31 99994-1160",
    "+5531999941160",
    "me criou o enzo",
    "o monstrinho que faz seus sonhos acontecerem",
    "your little monster that makes your dreams come true",
    "salva meu cartão pra você saber que sou eu",
    "save my card so you know it's me",
    "salva o cartão dele pra dúvida ou problema",
    "save his card for questions or trouble",
)

_SILENT = ("send_or_update_status",)

_KNOWN = (
    "hermes_plugins.plow_chat_platform",
    "hermes_plugins.plow_chat",
    "plow_chat",
)
_TAG = re.compile(r"^(MEDIA|VOICE):(/\S+)$")
_MEDIA_ROOTS = (
    Path("/var/lib/hermes/workspace"),
    Path("/srv"),
    Path("/opt/plow"),
)
_VOICE_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}


class Dropped:
    success = False
    error = "intentionally suppressed; nothing delivered"
    message_id = None
    suppressed = True
    raw_response = {"suppressed": True}
    retryable = False
    retry_after = None
    continuation_message_ids = ()
    error_kind = None


def _leftover_chat(args: tuple, kwargs: dict) -> str:
    chat = kwargs.get("chat_id") or kwargs.get("chat_uid")
    if chat:
        return str(chat)
    if args and str(args[0]).startswith("cht_"):
        return str(args[0])
    return ""


def _leftover_text(args: tuple, kwargs: dict) -> str:
    for key in ("content", "text", "message", "body"):
        value = kwargs.get(key)
        if isinstance(value, str) and value.strip():
            return value
    if len(args) >= 2 and args[1] is not None:
        return str(args[1])
    return ""


def _wrap_send(orig_send):
    async def send(self, *args, **kwargs):
        text = _leftover_text(args, kwargs)
        if credits_looks_like(text):
            if recently_told():
                log.debug("zoen-face dropped duplicate credits leftover")
                return Dropped()
            chat_id = _leftover_chat(args, kwargs)
            if not chat_id:
                log.warning("zoen-face credits leftover had no chat")
                return Dropped()
            body = credits_notice(credits_language())
            last = await orig_send(self, chat_id, body, metadata=kwargs.get("metadata"))
            if getattr(last, "success", False):
                mark_told(body)
                _answer_delivered(self)
            return last
        log.debug("zoen-face dropped leftover send")
        return Dropped()

    send.__name__ = "send"
    send.__qualname__ = "send"
    return send


def _answer_delivered(adapter):
    reception = getattr(adapter, "_zoen_reception", None)
    active = getattr(adapter, "_active_turn", None)
    turn = active.get() if active is not None else None
    if reception is not None and turn is not None:
        reception.answer_delivered(turn["chat_uid"], turn.get("source_message_id"))


def _with_purpose(send_sequence):
    async def sequence(self, args, turn, receipt=None):
        purpose = args.get("purpose", "answer")
        if purpose not in {"progress", "answer"}:
            raise ValueError("purpose must be progress or answer")
        previous = turn.get("reply_delivered", False)
        result = await send_sequence(self, {key: value for key, value in args.items() if key != "purpose"}, turn, receipt)
        if result.get("success"):
            if purpose == "progress":
                turn["reply_delivered"] = previous and not turn.get("inbound_handed_off")
            else:
                turn["reply_delivered"] = not turn.get("inbound_handed_off")
                _answer_delivered(self)
        return result
    return sequence


IMESSAGE = "zoen_imessage"
_FACTORY_SEND = "plow_send_sequence"
IMESSAGE_DESCRIPTION = (
    "Text the owner on iMessage. This is the ONLY way they see your words. "
    "Every update, question, link, photo, voice memo, and final answer must use this tool. "
    "Leftover prose is not delivered. If you skip this tool, they hear nothing. "
    "purpose=progress is an opening or update that does not complete the request. "
    "purpose=answer is the result."
)

WHO = (
    "You are Zoen. A Plow line or tree name is the number's label, not your name. "
    "People address you as Zoen. Never introduce yourself as that label. "
    "Never mention /help."
)


def claim_identity(module):
    """Keep the Plow facts, replace the per-turn 'You are {line}' prefix."""
    if getattr(module, "_zoen_identity", False):
        return
    if getattr(module, "_with_identity", None) is None:
        return
    facts = getattr(module, "_plow_facts", lambda _identity: "")

    def _with_identity(prompt, name, identity):
        return f"{WHO} {facts(identity)} {prompt}"

    module._with_identity = _with_identity
    module._zoen_identity = True


def configure_contract(module):
    # Keep Plow's owner-DM handler. Rename the model-facing tool so leftover
    # prose is never mistaken for a delivered bubble.
    schema = module.PLOW_SEND_SEQUENCE_SCHEMA
    schema["name"] = IMESSAGE
    schema["description"] = IMESSAGE_DESCRIPTION
    schema["parameters"]["properties"]["purpose"] = {
        "type": "string", "enum": ["progress", "answer"],
        "description": "progress is an update and never completes the request. answer is the result the owner should see.",
    }
    module._ANSWER_LAST = (
        f"Owner bubbles only go through {IMESSAGE}. Leftover prose is not delivered. "
        "Never skip that tool; if you do, they hear nothing. "
        "Every update, question, link, photo, voice memo, and final answer uses it. "
        "purpose=answer is the result; purpose=progress is a brief update that does "
        "not complete the request. Reception handles the opening for human messages; "
        "do not repeat it. Internal events do not need an opening and do not set language. "
        "Language follows the owner's last human message and VOICE.md, never this note. "
        "Do not narrate tool operations or routine bookkeeping. "
    )
    _publish_imessage(schema)


def _publish_imessage(schema):
    try:
        from tools.registry import registry
    except ImportError:
        return
    tools = getattr(registry, "_tools", None)
    if not isinstance(tools, dict):
        return
    lock = getattr(registry, "_lock", None)
    with lock if lock is not None else nullcontext():
        entry = tools.get(IMESSAGE) or tools.pop(_FACTORY_SEND, None)
        if entry is None:
            return
        entry.name = IMESSAGE
        entry.schema = schema
        if getattr(entry, "description", None) is not None:
            entry.description = IMESSAGE_DESCRIPTION
        tools[IMESSAGE] = entry
        tools.pop(_FACTORY_SEND, None)
        if hasattr(registry, "_generation"):
            registry._generation += 1


def _dropped(name: str):
    async def send(self, *args, **kwargs):
        log.debug("zoen-face dropped Hermes %s", name)
        return Dropped()

    send.__name__ = name
    send.__qualname__ = name
    return send


def media_file(raw: str) -> Path | None:
    candidate = Path(raw)
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    for root in _MEDIA_ROOTS:
        base = root.resolve() if root.exists() else root
        try:
            resolved.relative_to(base)
        except ValueError:
            continue
        return resolved
    return None


def tagged_paths(item: object) -> list[tuple[str, str]] | None:
    if not isinstance(item, dict) or item.get("type") != "text":
        return None
    body = item.get("body")
    if not isinstance(body, str):
        return None
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return None
    found: list[tuple[str, str]] = []
    for line in lines:
        match = _TAG.fullmatch(line)
        if match is None:
            return None
        found.append((match.group(1), match.group(2)))
    return found


def media_paths(item: object) -> list[str] | None:
    tagged = tagged_paths(item)
    if tagged is None:
        return None
    if any(kind != "MEDIA" for kind, _path in tagged):
        return None
    return [path for _kind, path in tagged]


def expand_items(items: list) -> list[tuple[str, object]]:
    chunks: list[tuple[str, object]] = []
    buffered: list = []

    def flush() -> None:
        if buffered:
            chunks.append(("seq", list(buffered)))
            buffered.clear()

    for item in items:
        tagged = tagged_paths(item)
        if tagged is None:
            buffered.append(item)
            continue
        flush()
        for kind, path in tagged:
            chunks.append(("voice" if kind == "VOICE" else "file", path))
    flush()
    return chunks


def _json(method: str, url: str, headers: dict[str, str], body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read()
            parsed = json.loads(raw.decode()) if raw else {}
            return {"ok": True, "status": resp.status, "body": parsed, "error": None}
    except HTTPError as exc:
        exc.read()
        return {"ok": False, "status": exc.code, "body": None, "error": str(exc.reason)}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"ok": False, "status": 0, "body": None, "error": str(exc)}


def _put(url: str, headers: dict[str, str], data: bytes) -> dict:
    req = Request(url, data=data, method="PUT", headers=headers)
    try:
        with urlopen(req, timeout=60) as resp:
            resp.read()
            return {"ok": True, "status": resp.status, "error": None}
    except HTTPError as exc:
        exc.read()
        return {"ok": False, "status": exc.code, "error": str(exc.reason)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def post_voicememo(chat_id: str, path: Path) -> object:
    ctype = _VOICE_TYPES.get(path.suffix.lower())
    if ctype is None:
        return None
    base = (os.environ.get("PLOW_API_BASE") or "").strip().rstrip("/")
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not base or not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = path.read_bytes()
    declared = _json(
        "POST",
        f"{base}/v1/chats/{quote(chat_id)}/attachments",
        headers,
        {
            "filename": path.name,
            "content_type": ctype,
            "size_bytes": len(payload),
        },
    )
    upload = declared.get("body") if declared.get("ok") else None
    if not isinstance(upload, dict) or not upload.get("uid") or not upload.get("upload_url"):
        return None
    stored = _put(str(upload["upload_url"]), dict(upload.get("upload_headers") or {}), payload)
    if not stored.get("ok"):
        return None
    sent = _json(
        "POST",
        f"{base}/v1/chats/{quote(chat_id)}/voicememo",
        headers,
        {"attachment_uid": upload["uid"]},
    )
    if not sent.get("ok"):
        return None
    return type("Result", (), {"success": True, "error": None, "message_id": None})()


def _retired_hello(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    body = str(item.get("body") or item.get("text") or "").lower()
    return any(needle in body for needle in _RETIRED_HELLO)


def _retired_text(text: str) -> bool:
    body = (text or "").lower()
    return any(needle in body for needle in _RETIRED_HELLO)


def _retired_payload(raw: object) -> bool:
    if not raw:
        return False
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    body = str(payload.get("body") or "") if isinstance(payload, dict) else text
    return _retired_text(body)


class _DroppedHTTP:
    status = 200

    def read(self) -> bytes:
        return b"{}"

    def __enter__(self) -> "_DroppedHTTP":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


_HTTP_FILTERED = False


def install_http_filter() -> None:
    """Drop retired hello POSTs that bypass zoen_imessage (face.py intro)."""
    global _HTTP_FILTERED
    if _HTTP_FILTERED:
        return
    _HTTP_FILTERED = True
    orig = urllib.request.urlopen

    def urlopen_filtered(*args, **kwargs):
        req = args[0] if args else kwargs.get("url")
        method = "GET"
        raw = kwargs.get("data")
        target = ""
        if isinstance(req, Request):
            method = req.get_method() or "GET"
            if raw is None:
                raw = req.data
            target = req.full_url
        elif req is not None:
            target = str(req)
        if method.upper() == "POST" and "/messages" in target and _retired_payload(raw):
            log.warning("zoen-face dropped retired hello HTTP POST")
            return _DroppedHTTP()
        return orig(*args, **kwargs)

    urllib.request.urlopen = urlopen_filtered


def _wrap_sequence(orig_seq, orig_attach, orig_voice):
    async def send_sequence(self, args, turn, receipt=None):
        items = [item for item in list((args or {}).get("items") or []) if not _retired_hello(item)]
        args = {**(args or {}), "items": items}
        if not items:
            return {"success": True, "completed": []}
        chunks = expand_items(items)
        if not any(kind in {"file", "voice"} for kind, _ in chunks):
            return await orig_seq(self, args, turn, receipt)
        chat_id = (turn or {}).get("chat_uid")
        report = receipt if receipt is not None else {}
        report.update(success=False, completed=[])
        for index, (kind, payload) in enumerate(chunks):
            if kind in {"file", "voice"}:
                path = media_file(str(payload))
                if (
                    path is None
                    or not chat_id
                    or (kind == "voice" and path.suffix.lower() not in _VOICE_TYPES)
                ):
                    report["failure"] = {"index": index, "status": "rejected", "error": "invalid media path or voice format"}
                    return report
                if kind == "file":
                    last = await orig_attach(self, chat_id, str(path))
                elif orig_voice is not None:
                    last = await orig_voice(self, chat_id, str(path))
                else:
                    last = await asyncio.to_thread(post_voicememo, chat_id, path)
            else:
                last = await orig_seq(self, {"items": payload}, turn)
            success = last.get("success", False) if isinstance(last, dict) else getattr(last, "success", False)
            if not success:
                report["failure"] = {"index": index, "status": "delivery_unknown", "error": "delivery failed or unconfirmed; inspect chat before retrying"}
                return report
            report["completed"].append({"index": index, "type": kind})
        report["success"] = bool(report["completed"])
        return report

    send_sequence.__name__ = "send_sequence"
    send_sequence.__qualname__ = "send_sequence"
    return send_sequence


def silence(adapter_cls) -> None:
    if getattr(adapter_cls, "_zoen_quiet", False):
        return
    adapter_cls._zoen_quiet = True
    install_http_filter()
    orig_seq = getattr(adapter_cls, "send_sequence", None)
    orig_attach = getattr(adapter_cls, "_send_attachment", None)
    orig_voice = getattr(adapter_cls, "send_voice", None)
    if getattr(adapter_cls, "send", None) is not None:
        adapter_cls.send = _wrap_send(adapter_cls.send)
    orig_final = getattr(adapter_cls, "_send_retry_is_final", None)
    if orig_final is not None:
        def send_retry_is_final(self, result):
            return isinstance(result, Dropped) or orig_final(self, result)

        adapter_cls._send_retry_is_final = send_retry_is_final
    for name in _SILENT:
        if getattr(adapter_cls, name, None) is None:
            continue
        setattr(adapter_cls, name, _dropped(name))
    if orig_seq is not None and orig_attach is not None:
        adapter_cls.send_sequence = _with_purpose(_wrap_sequence(orig_seq, orig_attach, orig_voice))
    log.info("zoen-face: leftover send dropped; owner bubbles use %s", IMESSAGE)


def _adapters():
    seen: set[int] = set()
    for name in _KNOWN:
        mod = sys.modules.get(name)
        if mod is None:
            try:
                mod = importlib.import_module(name)
            except ImportError:
                continue
        cls = getattr(mod, "PlowChatAdapter", None)
        if isinstance(cls, type) and id(cls) not in seen:
            seen.add(id(cls))
            yield cls
    for mod in list(sys.modules.values()):
        cls = getattr(mod, "PlowChatAdapter", None)
        if isinstance(cls, type) and callable(getattr(cls, "send", None)):
            if callable(getattr(cls, "send_sequence", None)) and id(cls) not in seen:
                seen.add(id(cls))
                yield cls


def silence_plow_adapter() -> None:
    wrapped = False
    for cls in _adapters():
        silence(cls)
        wrapped = True
    if not wrapped:
        log.warning("zoen-face: plow chat adapter missing, leftover send still live")
