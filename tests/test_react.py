#!/usr/bin/env python3
"""Run: python3 tests/test_react.py"""
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("react", ROOT / "skills/zoen/scripts/react.py")
react = importlib.util.module_from_spec(spec)
spec.loader.exec_module(react)


def test_latest_inbound_skips_outbound():
    calls = []

    def http(method, url, headers=None, body=None):
        calls.append((method, url, body))
        return {
            "ok": True,
            "status": 200,
            "error": None,
            "body": {
                "data": [
                    {"uid": "msg_out", "direction": "outbound"},
                    {"uid": "msg_in", "direction": "inbound"},
                ]
            },
        }

    os.environ["PLOW_API_BASE"] = "https://api.plow.co"
    os.environ["PLOW_AGENT_TOKEN"] = "plow_testtoken"
    os.environ["PLOW_HOME_CHANNEL"] = "cht_home"
    try:
        payload = react.add("like", http=http)
    finally:
        os.environ.pop("PLOW_AGENT_TOKEN", None)
    assert payload["ok"] is True
    assert payload["message"] == "msg_in"
    assert payload["chat"] == "cht_home"
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert calls[1][2] == {"operation": "add", "type": "like"}
    assert "/messages/msg_in/reactions" in calls[1][1]


def test_explicit_message_skips_list():
    calls = []

    def http(method, url, headers=None, body=None):
        calls.append((method, url, body))
        return {"ok": True, "status": 200, "error": None, "body": {}}

    os.environ["PLOW_API_BASE"] = "https://api.plow.co"
    os.environ["PLOW_AGENT_TOKEN"] = "plow_testtoken"
    try:
        payload = react.add("love", chat="cht_x", message="msg_given", http=http)
    finally:
        os.environ.pop("PLOW_AGENT_TOKEN", None)
    assert payload["ok"] is True
    assert payload["type"] == "love"
    assert len(calls) == 1
    assert "/chats/cht_x/messages/msg_given/reactions" in calls[0][1]


if __name__ == "__main__":
    test_latest_inbound_skips_outbound()
    test_explicit_message_skips_list()
    print("ok")
