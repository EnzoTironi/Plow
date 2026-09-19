#!/usr/bin/env python3
"""Connect Plow-managed accounts from iMessage, without a Zoen website.

    connect.py status google
    connect.py connect google
    connect.py status slack

Only lifecycle endpoints are exposed. Send connect_url in the owner's DM,
then check status after authorization and resume the saved task. Never send
the bearer token or treat a link as a completed connection.
"""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlencode, urlparse

from net import request

CONNECTORS = {"google": "gmail", "gmail": "gmail", "slack": "slack"}


def connection(action, connector, http=request):
    slug = CONNECTORS.get(connector)
    if not slug or action not in ("status", "connect"):
        return {"ok": False, "error": "supported: status|connect google|slack"}
    base = os.environ.get("PLOW_API_BASE", "https://api.plow.co").rstrip("/")
    if urlparse(base).scheme != "https":
        return {"ok": False, "error": "connector authorization requires HTTPS"}
    token = os.environ.get("PLOW_CONNECTOR_TOKEN") or os.environ.get("PLOW_AGENT_TOKEN")
    if not token:
        return {"ok": False, "error": "Plow connector credential unavailable"}
    endpoint = "status" if action == "status" else "connect-code"
    result = http("GET" if action == "status" else "POST",
                  f"{base}/v1/connectors/{slug}/{endpoint}",
                  headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if not result.get("ok"):
        return {"ok": False, "status": result.get("status"),
                "error": "Plow connection unavailable or this credential lacks connector permission"}
    body = result.get("body")
    if not isinstance(body, dict):
        return {"ok": False, "error": "invalid Plow connection response"}
    if action == "status":
        if not isinstance(body.get("connected"), bool):
            return {"ok": False, "error": "connection state missing"}
        return {"ok": True, "connector": connector, **{
            key: body.get(key) for key in ("connected", "account", "accounts")}}
    code = body.get("code")
    if not isinstance(code, str) or not code:
        return {"ok": False, "error": "authorization code missing"}
    return {"ok": True, "connected": False, "connector": connector,
            "connect_url": f"{base}/v1/connectors/{slug}/connect?{urlencode({'code': code})}",
            "instruction": "Send this short-lived link only in the owner's DM. Check status after consent; resume the original task only after verifying its account."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "connect"))
    parser.add_argument("connector", choices=CONNECTORS)
    args = parser.parse_args()
    result = connection(args.action, args.connector)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
