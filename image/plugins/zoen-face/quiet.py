"""iMessage posts only through plow_send_sequence and the Zoen intro.

Hermes leftover assistant text still reaches PlowChatAdapter.send().
That path is not the agent's voice. Empty transform_llm_output is
ignored, and NO_REPLY only drops when the turn advertised it, so the
gate is wrapping leftover send. Workspace photos are MEDIA: text
items on plow_send_sequence; the tool itself refuses paths, so those
items are expanded into the adapter's attachment POST.
"""
from __future__ import annotations

import importlib
import logging
import re
import sys
from pathlib import Path

log = logging.getLogger("zoen-face")

_SILENT = (
    "send",
    "send_or_update_status",
    "send_image_file",
    "send_voice",
    "send_video",
    "send_document",
)

_ADAPTER = "hermes_plugins.plow_chat_platform"
_MEDIA = re.compile(r"^MEDIA:(/\S+)$")
_MEDIA_ROOTS = (
    Path("/var/lib/hermes/workspace"),
    Path("/srv"),
    Path("/opt/plow"),
)


class Dropped:
    success = True
    error = None
    message_id = None


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


def media_paths(item: object) -> list[str] | None:
    if not isinstance(item, dict) or item.get("type") != "text":
        return None
    body = item.get("body")
    if not isinstance(body, str):
        return None
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return None
    found: list[str] = []
    for line in lines:
        match = _MEDIA.fullmatch(line)
        if match is None:
            return None
        found.append(match.group(1))
    return found


def expand_items(items: list) -> list[tuple[str, object]]:
    chunks: list[tuple[str, object]] = []
    buffered: list = []

    def flush() -> None:
        if buffered:
            chunks.append(("seq", list(buffered)))
            buffered.clear()

    for item in items:
        paths = media_paths(item)
        if paths is None:
            buffered.append(item)
            continue
        flush()
        for path in paths:
            chunks.append(("file", path))
    flush()
    return chunks


def _wrap_sequence(orig_seq, orig_attach):
    async def send_sequence(self, args, turn, receipt=None):
        items = list((args or {}).get("items") or [])
        chunks = expand_items(items)
        if not any(kind == "file" for kind, _ in chunks):
            return await orig_seq(self, args, turn, receipt)
        chat_id = (turn or {}).get("chat_uid")
        last = None
        delivered = False
        for kind, payload in chunks:
            if kind == "file":
                path = media_file(str(payload))
                if path is None or not chat_id:
                    log.warning("zoen-face skipped MEDIA path %s", payload)
                    continue
                last = await orig_attach(self, chat_id, str(path))
                delivered = True
                continue
            last = await orig_seq(self, {"items": payload}, turn, receipt)
            delivered = True
        if not delivered:
            return Dropped()
        return last

    send_sequence.__name__ = "send_sequence"
    send_sequence.__qualname__ = "send_sequence"
    return send_sequence


def silence(adapter_cls) -> None:
    if getattr(adapter_cls, "_zoen_quiet", False):
        return
    adapter_cls._zoen_quiet = True
    orig_seq = getattr(adapter_cls, "send_sequence", None)
    orig_attach = getattr(adapter_cls, "_send_attachment", None)
    for name in _SILENT:
        if getattr(adapter_cls, name, None) is None:
            continue
        setattr(adapter_cls, name, _dropped(name))
    if orig_seq is not None and orig_attach is not None:
        adapter_cls.send_sequence = _wrap_sequence(orig_seq, orig_attach)
    log.info("zoen-face: iMessage send is plow_send_sequence only")


def silence_plow_adapter() -> None:
    # plow-chat-platform is listed first; bind after that module is loaded.
    mod = sys.modules.get(_ADAPTER)
    if mod is None:
        try:
            mod = importlib.import_module(_ADAPTER)
        except ImportError:
            log.warning("zoen-face: plow chat adapter missing, leftover send still live")
            return
    cls = getattr(mod, "PlowChatAdapter", None)
    if cls is None:
        log.warning("zoen-face: PlowChatAdapter missing, leftover send still live")
        return
    silence(cls)
