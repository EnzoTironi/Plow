#!/usr/bin/env python3
"""Tapback on a chat message. Bones only: no voice.

    react.py like
    react.py love --message msg_xxx
    react.py like --chat cht_xxx

Default chat: PLOW_HOME_CHANNEL. Default target: newest inbound.
Auth: PLOW_API_BASE + PLOW_AGENT_TOKEN.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import request  # noqa: E402

KINDS = ("love", "like", "dislike", "laugh", "emphasize", "question")
Http = Callable[..., dict]


def _out(payload: dict) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload.get("ok", True) else 1


def credentials() -> tuple[str, dict[str, str]]:
    base = (os.environ.get("PLOW_API_BASE") or "").strip().rstrip("/")
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not base or not token:
        raise SystemExit("react: set PLOW_API_BASE and PLOW_AGENT_TOKEN")
    return base, {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def chat_uid(explicit: str | None) -> str:
    value = (explicit or os.environ.get("PLOW_HOME_CHANNEL") or "").strip()
    if not value.startswith("cht_"):
        raise SystemExit("react: pass --chat cht_... or set PLOW_HOME_CHANNEL")
    return value


def latest_inbound(base: str, headers: dict[str, str], chat: str, http: Http = request) -> str:
    result = http("GET", f"{base}/v1/chats/{quote(chat)}/messages?limit=20", headers=headers)
    body = result.get("body") if result.get("ok") else None
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise SystemExit(f"react: could not list messages: {result.get('error') or result.get('status')}")
    for item in rows:
        if isinstance(item, dict) and item.get("direction") == "inbound" and str(item.get("uid") or "").startswith("msg_"):
            return str(item["uid"])
    raise SystemExit("react: no inbound message")


def add(
    kind: str,
    chat: str | None = None,
    message: str | None = None,
    http: Http = request,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise SystemExit(f"react: type must be one of {', '.join(KINDS)}")
    base, headers = credentials()
    chat = chat_uid(chat)
    target = (message or "").strip() or latest_inbound(base, headers, chat, http=http)
    if not target.startswith("msg_"):
        raise SystemExit("react: --message must be msg_...")
    url = f"{base}/v1/chats/{quote(chat)}/messages/{quote(target)}/reactions"
    result = http(
        "POST",
        url,
        headers=headers,
        body={"operation": "add", "type": kind},
    )
    return {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "error": result.get("error"),
        "chat": chat,
        "message": target,
        "type": kind,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("type", choices=KINDS, help="iMessage tapback")
    parser.add_argument("--chat", help="cht_... (default PLOW_HOME_CHANNEL)")
    parser.add_argument("--message", help="msg_... (default newest inbound)")
    return parser


def main(argv: list[str] | None = None, http: Http = request) -> int:
    args = build_parser().parse_args(argv)
    return _out(add(args.type, chat=args.chat, message=args.message, http=http))


if __name__ == "__main__":
    raise SystemExit(main())
