"""Preserve native final delivery, with explicit progress and local media support."""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import re
import sys
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
        result = await orig_send(self, *args, **kwargs)
        metadata = kwargs.get("metadata") or (args[3] if len(args) > 3 else None) or {}
        if metadata.get("notify") and getattr(result, "success", False) and getattr(result, "message_id", None):
            _answer_delivered(self)
        return result

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


def configure_contract(module):
    # Extend the registered schema in place; the native handler and its owner-DM
    # authorization remain responsible for accepting the call.
    schema = module.PLOW_SEND_SEQUENCE_SCHEMA
    schema["parameters"]["properties"]["purpose"] = {
        "type": "string", "enum": ["progress", "answer"],
        "description": "Use progress for an opening or update; it never completes the answer. Default answer means these messages are the final result.",
    }
    module._ANSWER_LAST = (
        "Write the final answer last; normal final text is delivered automatically. "
        "For multiple final bubbles or media use plow_send_sequence with purpose=answer, "
        "then do not repeat that answer in prose. A brief meaningful progress update uses "
        "purpose=progress and does not complete the request. Reception handles the opening "
        "for human messages; do not repeat it. Internal events do not need an opening. "
        "Do not narrate tool operations or routine bookkeeping. "
    )


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


def _wrap_sequence(orig_seq, orig_attach, orig_voice):
    async def send_sequence(self, args, turn, receipt=None):
        items = list((args or {}).get("items") or [])
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
    log.info("zoen-face: native final delivery enabled; progress is separate")


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
