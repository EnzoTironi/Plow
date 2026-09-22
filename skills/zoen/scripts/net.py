#!/usr/bin/env python3
"""Tiny JSON HTTP helper. Stdlib only."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: Any = None,
    timeout: int = 20,
) -> dict:
    raw: bytes | None = None
    hdrs = dict(headers or {})
    hdrs.setdefault("User-Agent", "Zoen")
    if body is not None:
        raw = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=raw, method=method.upper(), headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            parsed: Any = None
            if text.strip():
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = text
            return {"ok": True, "status": resp.status, "body": parsed, "error": None}
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")
        parsed = None
        if err_text.strip():
            try:
                parsed = json.loads(err_text)
            except json.JSONDecodeError:
                parsed = err_text
        return {"ok": False, "status": exc.code, "body": parsed, "error": str(exc.reason)}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status": 0, "body": None, "error": str(exc)}
