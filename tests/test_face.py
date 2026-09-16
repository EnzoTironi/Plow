#!/usr/bin/env python3
"""Run: python3 tests/test_face.py"""
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("face", ROOT / "skills/zoen/scripts/face.py")
face = importlib.util.module_from_spec(spec)
spec.loader.exec_module(face)

ME = {
    "line": {"uid": "ln_p1", "provider_key": "+15555550100", "display_name": "Willow"},
    "chats": [
        {
            "uid": "cht_home",
            "status": "active",
            "participants": [
                {"type": "agent", "relationship": "self"},
                {"type": "member", "role": "owner", "provider_key": "a@b.c"},
            ],
        }
    ],
    "agent": {"uid": "abc123", "name": "plow-agent"},
}


def test_vcard_carries_name_photo_and_number():
    jpeg = b"\xff\xd8\xff" + b"x" * 80
    card = face.vcard("Zoen", "+15555550100", jpeg).decode("utf-8")
    assert "FN:Zoen" in card
    assert "TEL;TYPE=CELL,VOICE,pref:+15555550100" in card
    assert "PHOTO;ENCODING=b;TYPE=JPEG:" in card
    assert "BEGIN:VCARD" in card
    assert "\r\n" in card
    folded = [line for line in card.split("\r\n") if line.startswith(" ") or line.startswith("PHOTO")]
    assert folded
    assert all(len(line.encode()) <= 75 for line in card.split("\r\n") if line)


def test_apply_renames_and_sends_once():
    calls = []

    def http(method, url, headers=None, body=None):
        calls.append((method, url, body, (headers or {}).get("Authorization", "")[:12]))
        if url.endswith("/v1/agents/me"):
            return {"ok": True, "status": 200, "error": None, "body": ME}
        if "/v1/agents/abc123" in url and method == "PATCH":
            assert body == {"name": "Zoen"}
            return {"ok": True, "status": 200, "error": None, "body": {"name": "Zoen"}}
        if url.endswith("/messages?limit=20"):
            return {"ok": True, "status": 200, "error": None, "body": {"data": []}}
        if url.endswith("/attachments"):
            assert body["filename"] == "Zoen.vcf"
            assert body["content_type"] == "text/vcard"
            return {
                "ok": True,
                "status": 201,
                "error": None,
                "body": {
                    "uid": "att_card",
                    "upload_url": "https://upload.example/put",
                    "upload_headers": {"Content-Type": "text/vcard"},
                },
            }
        if url.endswith("/messages"):
            assert body == {"body": "", "attachment_uids": ["att_card"]}
            return {"ok": True, "status": 201, "error": None, "body": {"uid": "msg_card"}}
        raise AssertionError(url)

    puts = []

    def put(url, headers, data):
        puts.append((url, headers, data[:20]))
        assert url == "https://upload.example/put"
        assert b"BEGIN:VCARD" in data
        return {"ok": True, "status": 200, "error": None}

    os.environ["PLOW_API_BASE"] = "https://api.plow.co"
    os.environ["PLOW_AGENT_TOKEN"] = "plow_agent"
    os.environ["PLOW_ACCOUNT_TOKEN"] = "plow_account"
    os.environ["ZOEN_CARD_PHOTO"] = str(ROOT / "docs/zoen-card.jpg")
    try:
        payload = face.apply(http=http, put=put)
    finally:
        os.environ.pop("PLOW_AGENT_TOKEN", None)
        os.environ.pop("PLOW_ACCOUNT_TOKEN", None)
        os.environ.pop("ZOEN_CARD_PHOTO", None)
    assert payload["ok"] is True
    assert payload["name"] == "Zoen"
    assert payload["attachment"] == "att_card"
    assert payload["rename"]["ok"] is True
    assert puts and puts[0][0] == "https://upload.example/put"
    assert any(item[0] == "PATCH" for item in calls)


def test_apply_skips_when_card_already_went():
    def http(method, url, headers=None, body=None):
        if url.endswith("/v1/agents/me"):
            return {"ok": True, "status": 200, "error": None, "body": ME}
        if url.endswith("/messages?limit=20"):
            return {
                "ok": True,
                "status": 200,
                "error": None,
                "body": {
                    "data": [
                        {
                            "direction": "outbound",
                            "attachments": [{"filename": "Zoen.vcf"}],
                        }
                    ]
                },
            }
        raise AssertionError(url)

    os.environ["PLOW_API_BASE"] = "https://api.plow.co"
    os.environ["PLOW_AGENT_TOKEN"] = "plow_agent"
    os.environ["PLOW_ACCOUNT_TOKEN"] = ""
    try:
        payload = face.apply(http=http, put=lambda *a: (_ for _ in ()).throw(AssertionError("put")))
    finally:
        os.environ.pop("PLOW_AGENT_TOKEN", None)
    assert payload["ok"] is True
    assert payload["skipped"] == "already sent"


def test_hello_copy_fits_imessage():
    for bubbles in face.HELLO.values():
        assert len(bubbles) == 3
        for bubble in bubbles:
            assert not bubble.endswith(".")
            assert len(bubble.splitlines()) <= 2
            assert "—" not in bubble
    assert "I'm Zoen" in face.HELLO["en"][0]
    assert "save my card" in face.HELLO["en"][1]
    assert "what's your dream?" in face.HELLO["en"][2]
    assert "eu sou o Zoen" in face.HELLO["pt"][0]
    assert face.HELLO["pt"][2] == "qual é o seu sonho?"


def test_intro_sends_hello_then_card():
    calls = []
    naps = []

    def http(method, url, headers=None, body=None):
        calls.append((method, url, body))
        if url.endswith("/v1/agents/me"):
            return {"ok": True, "status": 200, "error": None, "body": ME}
        if url.endswith("/messages?limit=20"):
            return {
                "ok": True,
                "status": 200,
                "error": None,
                "body": {"data": [{"direction": "inbound", "body": "hey"}]},
            }
        if url.endswith("/attachments"):
            return {
                "ok": True,
                "status": 201,
                "error": None,
                "body": {
                    "uid": "att_card",
                    "upload_url": "https://upload.example/put",
                    "upload_headers": {"Content-Type": "text/vcard"},
                },
            }
        if url.endswith("/messages"):
            return {"ok": True, "status": 201, "error": None, "body": {"uid": "msg_x"}}
        raise AssertionError(url)

    def put(url, headers, data):
        assert b"BEGIN:VCARD" in data
        return {"ok": True, "status": 200, "error": None}

    os.environ["PLOW_API_BASE"] = "https://api.plow.co"
    os.environ["PLOW_AGENT_TOKEN"] = "plow_agent"
    os.environ["PLOW_ACCOUNT_TOKEN"] = ""
    os.environ["ZOEN_CARD_PHOTO"] = str(ROOT / "docs/zoen-card.jpg")
    try:
        payload = face.intro(http=http, put=put, nap=naps.append)
    finally:
        os.environ.pop("PLOW_AGENT_TOKEN", None)
        os.environ.pop("PLOW_ACCOUNT_TOKEN", None)
        os.environ.pop("ZOEN_CARD_PHOTO", None)
    assert payload["ok"] is True
    assert payload["language"] == "en"
    assert payload["hello"][0].startswith("hey, I'm Zoen")
    assert payload["hello"][-1] == "what's your dream?"
    assert payload["attachment"] == "att_card"
    texts = [body["body"] for method, url, body in calls if method == "POST" and url.endswith("/messages") and body.get("body")]
    assert texts == list(face.HELLO["en"])
    assert naps == [1.75, 2.0, 1.75]


def test_intro_uses_portuguese_on_portuguese_hello():
    def http(method, url, headers=None, body=None):
        if url.endswith("/v1/agents/me"):
            return {"ok": True, "status": 200, "error": None, "body": ME}
        if url.endswith("/messages?limit=20"):
            return {
                "ok": True,
                "status": 200,
                "error": None,
                "body": {"data": [{"direction": "inbound", "body": "Oi, tudo bem"}]},
            }
        if url.endswith("/attachments"):
            return {
                "ok": True,
                "status": 201,
                "error": None,
                "body": {
                    "uid": "att_card",
                    "upload_url": "https://upload.example/put",
                    "upload_headers": {},
                },
            }
        if url.endswith("/messages"):
            return {"ok": True, "status": 201, "error": None, "body": {}}
        raise AssertionError(url)

    os.environ["PLOW_API_BASE"] = "https://api.plow.co"
    os.environ["PLOW_AGENT_TOKEN"] = "plow_agent"
    os.environ["PLOW_ACCOUNT_TOKEN"] = ""
    os.environ["ZOEN_CARD_PHOTO"] = str(ROOT / "docs/zoen-card.jpg")
    try:
        payload = face.intro(http=http, put=lambda *a: {"ok": True, "status": 200, "error": None}, nap=lambda s: None)
    finally:
        os.environ.pop("PLOW_AGENT_TOKEN", None)
        os.environ.pop("PLOW_ACCOUNT_TOKEN", None)
        os.environ.pop("ZOEN_CARD_PHOTO", None)
    assert payload["language"] == "pt"
    assert "eu sou o Zoen" in payload["hello"][0]
    assert payload["hello"][-1] == "qual é o seu sonho?"


def test_intro_skips_when_we_already_talked():
    def http(method, url, headers=None, body=None):
        if url.endswith("/v1/agents/me"):
            return {"ok": True, "status": 200, "error": None, "body": ME}
        if url.endswith("/messages?limit=20"):
            return {
                "ok": True,
                "status": 200,
                "error": None,
                "body": {
                    "data": [
                        {"direction": "outbound", "body": "on it", "attachments": []},
                        {
                            "direction": "outbound",
                            "body": "",
                            "attachments": [{"filename": "Zoen.vcf"}],
                        },
                    ]
                },
            }
        raise AssertionError(url)

    os.environ["PLOW_API_BASE"] = "https://api.plow.co"
    os.environ["PLOW_AGENT_TOKEN"] = "plow_agent"
    os.environ["PLOW_ACCOUNT_TOKEN"] = ""
    try:
        payload = face.intro(http=http, put=lambda *a: (_ for _ in ()).throw(AssertionError("put")), nap=lambda s: None)
    finally:
        os.environ.pop("PLOW_AGENT_TOKEN", None)
        os.environ.pop("PLOW_ACCOUNT_TOKEN", None)
    assert payload["skipped"] == "already sent"


if __name__ == "__main__":
    test_vcard_carries_name_photo_and_number()
    test_apply_renames_and_sends_once()
    test_apply_skips_when_card_already_went()
    test_hello_copy_fits_imessage()
    test_intro_sends_hello_then_card()
    test_intro_uses_portuguese_on_portuguese_hello()
    test_intro_skips_when_we_already_talked()
    print("ok")
