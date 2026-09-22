"""Owner-facing copy when Plow LLM credits are gone.

Not an ack. The leftover Hermes 402 blob never ships; this is the
bubble instead. Same shape as every other Zoen text: two lines, no
trailing period, their language.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

NOTICE = {
    "pt": (
        "acabaram os créditos da plow\n"
        "recarrega em app.plow.co/dashboard pra eu continuar"
    ),
    "en": (
        "plow credits ran out\n"
        "top up at app.plow.co/dashboard so i can keep going"
    ),
    "es": (
        "se acabaron los créditos de plow\n"
        "recarga en app.plow.co/dashboard para que yo siga"
    ),
    "fr": (
        "plus de crédits plow\n"
        "recharge sur app.plow.co/dashboard pour que je continue"
    ),
}


def notice(lang: str | None) -> str:
    key = (lang or "").strip().lower()[:2]
    return NOTICE.get(key) or NOTICE["pt"]


def language(home: str | None = None) -> str:
    root = (home or os.environ.get("HERMES_HOME") or "").strip()
    if not root:
        return "pt"
    path = Path(root) / "zoen" / "VOICE.md"
    if not path.is_file():
        return "pt"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("language:"):
            token = line.split(":", 1)[1].strip().split()[0].lower()
            if len(token) >= 2 and token[:2].isalpha():
                return token[:2]
    return "pt"


def _blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except TypeError:
            value = str(value)
    return value.lower()


def looks_like(text: Any) -> bool:
    blob = _blob(text)
    if "out of plow credits" in blob or "billing or credits exhausted" in blob:
        return True
    if "app.plow.co/dashboard" in blob and any(
        word in blob for word in ("credit", "crédit", "crédito")
    ):
        return True
    return "credit" in blob and "402" in blob


def is_notice(text: Any) -> bool:
    if looks_like(text):
        return True
    blob = " ".join(_blob(text).split())
    if not blob:
        return False
    return blob in {" ".join(body.lower().split()) for body in NOTICE.values()}


def owner_copy(text: Any, home: str | None = None, channel: str = "imessage") -> str | None:
    """The ready notice, empty when this channel was already told, or None."""
    if not is_notice(text):
        return None
    if recently_told(home, channel):
        return ""
    return notice(language(home))


def result_is_credits(result: dict[str, Any] | None) -> bool:
    if not result or result.get("ok"):
        return False
    if result.get("status") == 402:
        return True
    return looks_like(result.get("body")) or looks_like(result.get("error"))


def stamp_path(home: str | None = None, channel: str = "imessage") -> Path | None:
    root = (home or os.environ.get("HERMES_HOME") or "").strip()
    if not root:
        return None
    name = "credits-whatsapp" if channel == "whatsapp" else "credits"
    return Path(root) / "zoen" / name


def recently_told(home: str | None = None, channel: str = "imessage") -> bool:
    path = stamp_path(home, channel)
    return path is not None and path.is_file()


def clear_told(home: str | None = None, channel: str = "imessage") -> None:
    path = stamp_path(home, channel)
    if path is not None and path.is_file():
        path.unlink()


def mark_told(body: str, home: str | None = None, channel: str = "imessage") -> None:
    path = stamp_path(home, channel)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body + "\n", encoding="utf-8")
