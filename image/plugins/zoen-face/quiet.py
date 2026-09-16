"""iMessage posts only through plow_send_sequence and the Zoen intro.

Hermes leftover assistant text still reaches PlowChatAdapter.send().
That path is not the agent's voice. Empty transform_llm_output is
ignored, and NO_REPLY only drops when the turn advertised it, so the
gate is wrapping the adapter methods that POST to chat.
"""
from __future__ import annotations

import importlib
import logging
import sys

log = logging.getLogger("zoen-face")

_SILENT = (
    "send",
    "send_or_update_status",
    "send_image_file",
    "send_voice",
    "send_video",
    "send_document",
    "_send_attachment",
)

_ADAPTER = "hermes_plugins.plow_chat_platform"


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


def silence(adapter_cls) -> None:
    if getattr(adapter_cls, "_zoen_quiet", False):
        return
    adapter_cls._zoen_quiet = True
    for name in _SILENT:
        if getattr(adapter_cls, name, None) is None:
            continue
        setattr(adapter_cls, name, _dropped(name))
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
