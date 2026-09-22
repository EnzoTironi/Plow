#!/usr/bin/env python3
"""Run: python3 tests/test_zoen_face_quiet.py"""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import time
import urllib.request
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "zoen_face_quiet", ROOT / "image/plugins/zoen-face/quiet.py"
)
quiet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quiet)


def _adapter():
    class Adapter:
        def __init__(self):
            self.posted = []

        async def send(self, chat_id, content, reply_to=None, metadata=None):
            self.posted.append(("send", content))
            return SimpleNamespace(success=True, error=None)

        async def send_or_update_status(self, chat_id, status_key, content, metadata=None):
            self.posted.append(("status", content))
            return "status"

        async def send_image_file(self, chat_id, image_path, caption=None, **_kwargs):
            self.posted.append(("image", image_path))
            return "image"

        async def send_voice(self, chat_id, audio_path, caption=None, **_kwargs):
            self.posted.append(("voice", audio_path))
            return SimpleNamespace(success=True, error=None)

        async def send_sequence(self, args, turn, receipt=None):
            self.posted.append(("sequence", args))
            return {"success": True, "completed": []}

        async def _send_attachment(self, chat_id, path, *, caption=None, filename=None):
            self.posted.append(("file", path))
            return SimpleNamespace(success=True, error=None)

        async def send_typing(self, chat_id, metadata=None):
            self.posted.append(("typing", chat_id))
            return "typing"

    return Adapter


def test_leftover_credits_error_becomes_the_dashboard_bubble():
    Adapter = _adapter()
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        (Path(home) / "zoen").mkdir()
        (Path(home) / "zoen" / "VOICE.md").write_text("language: en\n")
        try:
            quiet.silence(Adapter)
            box = Adapter()
            blob = (
                'HTTP 402: {"detail":"You\'re out of Plow credits. '
                'Top up at app.plow.co/dashboard to keep going."}'
            )
            result = asyncio.run(box.send("cht_x", blob))
            asyncio.run(box.send("cht_x", blob))
        finally:
            os.environ.pop("HERMES_HOME", None)
    assert box.posted == [("send", quiet.credits_notice("en"))]
    assert result.success is True


def test_credits_notice_stays_quiet_until_a_normal_reply():
    Adapter = _adapter()
    blob = (
        'HTTP 402: {"detail":"You\'re out of Plow credits. '
        'Top up at app.plow.co/dashboard to keep going."}'
    )
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        (Path(home) / "zoen").mkdir()
        (Path(home) / "zoen" / "VOICE.md").write_text("language: pt\n")
        try:
            quiet.silence(Adapter)
            box = Adapter()
            asyncio.run(box.send("cht_x", blob))
            stamp = Path(home) / "zoen" / "credits"
            old = time.time() - 3 * 60 * 60
            os.utime(stamp, (old, old))
            asyncio.run(box.send("cht_x", blob))
            asyncio.run(box.send_sequence(
                {"items": [{"type": "text", "body": quiet.credits_notice("pt")}]},
                {"chat_uid": "cht_x"},
            ))
            asyncio.run(box.send_sequence(
                {"items": [{"type": "text", "body": "voltei"}]},
                {"chat_uid": "cht_x"},
            ))
            asyncio.run(box.send("cht_x", blob))
        finally:
            os.environ.pop("HERMES_HOME", None)
    assert box.posted == [
        ("send", quiet.credits_notice("pt")),
        ("sequence", {"items": [{"type": "text", "body": "voltei"}]}),
        ("send", quiet.credits_notice("pt")),
    ]


def test_normal_final_is_dropped():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    result = asyncio.run(box.send("cht_x", "Still building. Ending turn."))
    assert box.posted == []
    assert result.suppressed is True


def test_contract_renames_send_and_forbids_leftover():
    module = SimpleNamespace(
        PLOW_SEND_SEQUENCE_SCHEMA={
            "name": "plow_send_sequence",
            "description": "old",
            "parameters": {"properties": {}},
        }
    )
    quiet.configure_contract(module)
    assert module.PLOW_SEND_SEQUENCE_SCHEMA["name"] == "zoen_imessage"
    assert "ONLY way they see your words" in module.PLOW_SEND_SEQUENCE_SCHEMA["description"]
    assert "zoen_imessage" in module._ANSWER_LAST
    assert "not delivered" in module._ANSWER_LAST
    assert "Never skip" in module._ANSWER_LAST
    assert "delivered automatically" not in module._ANSWER_LAST


def test_contract_moves_scoped_factory_send_to_zoen_imessage():
    entry = SimpleNamespace(
        name="plow_send_sequence",
        schema={"name": "plow_send_sequence"},
        description="old",
    )
    scoped = {"plow_send_sequence": entry}
    fake = SimpleNamespace(
        _tools={},
        _scoped_tools={"/tmp/home": scoped},
        _lock=nullcontext(),
        _generation=1,
        register=lambda *args, **kwargs: None,
    )
    sys.modules["tools"] = sys.modules.get("tools") or SimpleNamespace()
    previous = sys.modules.get("tools.registry")
    sys.modules["tools.registry"] = SimpleNamespace(registry=fake)
    try:
        module = SimpleNamespace(
            PLOW_SEND_SEQUENCE_SCHEMA={
                "name": "plow_send_sequence",
                "description": "old",
                "parameters": {"properties": {}},
            }
        )
        quiet.configure_contract(module)
        assert "plow_send_sequence" not in scoped
        assert scoped["zoen_imessage"].name == "zoen_imessage"
        assert scoped["zoen_imessage"].schema["name"] == "zoen_imessage"
        assert module.PLOW_SEND_SEQUENCE_SCHEMA["name"] == "zoen_imessage"
    finally:
        if previous is None:
            sys.modules.pop("tools.registry", None)
        else:
            sys.modules["tools.registry"] = previous


def test_retired_hello_http_post_is_dropped():
    quiet.install_http_filter()
    req = urllib.request.Request(
        "https://example.invalid/v1/chats/cht_x/messages",
        data=json.dumps({"body": "a gente te ajuda. +55 31 99994-1160", "format": "none"}).encode(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=1) as resp:
        assert resp.status == 200
        assert json.loads(resp.read()) == {}


def test_retired_hello_is_dropped():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    args = {
        "items": [
            {"type": "text", "body": "a gente te ajuda. +55 31 99994-1160"},
            {"type": "text", "body": "shipped"},
        ]
    }
    result = asyncio.run(box.send_sequence(args, {"chat_uid": "cht_x"}))
    assert result["success"] is True
    assert box.posted == [("sequence", {"items": [{"type": "text", "body": "shipped"}]})]


def test_whatsapp_owner_phone_is_the_handle_digits():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    adapter = SimpleNamespace(
        _chats={"cht_home": {"owner": True}},
        _send_guard=lambda uid: None,
    )
    module = SimpleNamespace(
        _owner_dm=lambda chat: chat.get("owner", False),
        _owner_handle=lambda chat: "+55 (11) 99999-9999",
    )
    assert whatsapp.owner_phone(adapter, module) == "5511999999999"
    module._owner_handle = lambda chat: "ana@example.com"
    assert whatsapp.owner_phone(adapter, module) == ""
    me = {
        "chats": [{
            "uid": "cht_home",
            "status": "active",
            "participants": [
                {"type": "agent", "relationship": "self"},
                {"type": "member", "role": "owner", "provider_type": "imessage", "provider_key": "+55 (11) 99999-9999"},
            ],
        }],
    }
    assert whatsapp.phone_from_identity(me) == "5511999999999"
    assert whatsapp.home_chat_uid(me) == "cht_home"
    me["chats"].append({
        "uid": "cht_android",
        "status": "active",
        "participants": [
            {"type": "agent", "relationship": "self"},
            {"type": "member", "role": "owner", "provider_type": "imessage", "provider_key": "+55 31 98888-7777"},
        ],
    })
    assert whatsapp.pairing_chat_uids(me) == ["cht_home", "cht_android"]
    assert whatsapp.home_chat_uid(me) == "cht_home"
    me["chats"][0]["participants"][1]["provider_key"] = "ana@example.com"
    me["chats"][0]["participants"][1]["provider_type"] = "email"
    assert whatsapp.pairing_chat_uids(me) == ["cht_home", "cht_android"]
    me["chats"].append({
        "uid": "cht_mail",
        "status": "active",
        "participants": [
            {"type": "agent", "relationship": "self"},
            {"type": "member", "role": "owner", "provider_type": "imessage", "provider_key": "enzo@example.com"},
        ],
    })
    assert whatsapp.pairing_chat_uids(me) == ["cht_home", "cht_android", "cht_mail"]
    assert whatsapp.phone_from_identity(me) == "5531988887777"
    assert whatsapp.phone_from_contacts([
        {"role": "member", "provider_key": "+15555550100"},
        {"role": "owner", "provider_key": "+55 (11) 99999-9999"},
    ]) == "5511999999999"


def test_whatsapp_poll_starts_when_the_line_connects():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_boot", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)

    class Adapter:
        def __init__(self):
            self.ready = False

        async def connect(self):
            self.ready = True
            return True

    previous = os.environ.get("ZOEN_OAUTH_RELAY_URL")
    os.environ["ZOEN_OAUTH_RELAY_URL"] = "http://127.0.0.1:9"
    try:
        whatsapp.bind(SimpleNamespace())
        whatsapp.install(Adapter, SimpleNamespace())
        box = Adapter()
        assert whatsapp._TASK is None
        asyncio.run(box.connect())
        assert box.ready is True
        assert whatsapp._TASK is not None
        whatsapp._TASK.cancel()
    finally:
        if previous is None:
            os.environ.pop("ZOEN_OAUTH_RELAY_URL", None)
        else:
            os.environ["ZOEN_OAUTH_RELAY_URL"] = previous


def test_whatsapp_credits_follow_the_inbound_and_imessage_stays_on_imessage():
    blob = (
        'Billing or credits exhausted: HTTP 402: {"detail":"You\'re out of Plow credits. '
        'Top up at app.plow.co/dashboard to keep going."}'
    )

    class Adapter(_adapter()):
        async def _process_message_background(self, event, session_key):
            return await self.send("cht_x", blob)

    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        (Path(home) / "zoen").mkdir()
        (Path(home) / "zoen" / "VOICE.md").write_text("language: pt\n")
        sent = []

        async def deliver(text):
            sent.append(text)
            return True

        quiet.WHATSAPP_DELIVER = deliver
        try:
            quiet.silence(Adapter)
            box = Adapter()
            whatsapp_event = SimpleNamespace(zoen_whatsapp={"to": "5511999999999"})
            asyncio.run(box._process_message_background(whatsapp_event, "wa"))
            imessage_event = SimpleNamespace()
            asyncio.run(box._process_message_background(imessage_event, "im"))
        finally:
            quiet.WHATSAPP_DELIVER = None
            os.environ.pop("HERMES_HOME", None)
    assert sent == [quiet.credits_notice("pt")]
    assert box.posted == [("send", quiet.credits_notice("pt"))]
    assert quiet.WHATSAPP.get() is None


def test_agent_secret_is_stable_for_the_volume():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_secret", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    previous = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        try:
            first = whatsapp._agent_secret()
            second = whatsapp._agent_secret()
        finally:
            if previous is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous
    assert first == second
    assert len(first) >= 43


def test_pairing_code_stays_on_the_volume_and_opens_whatsapp():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_code", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    previous = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        try:
            first = whatsapp._pairing_code()
            second = whatsapp._pairing_code()
            text = whatsapp.pairing_message(first)
        finally:
            if previous is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous
    assert first == second
    assert len(first) == 6 and first.isdigit()
    assert f"https://wa.me/553798136141?text={first}" in text


def test_pairing_code_reaches_every_phone_chat():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_announce", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    previous_home = os.environ.get("HERMES_HOME")
    previous_api = os.environ.get("PLOW_API_BASE")
    previous_token = os.environ.get("PLOW_AGENT_TOKEN")
    posted = []

    async def fake_request(method, url, token, payload=None, extra=None):
        posted.append((method, url, payload))
        return {}

    whatsapp._request = fake_request
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["PLOW_API_BASE"] = "https://plow.example"
        os.environ["PLOW_AGENT_TOKEN"] = "agt_test"
        try:
            code = whatsapp._pairing_code()
            asyncio.run(whatsapp._announce_chats("agt_test", ["cht_home", "cht_android"], code))
            asyncio.run(whatsapp._announce_chats("agt_test", ["cht_home", "cht_android"], code))
            adapter = SimpleNamespace(
                _chats={"cht_new": {"owner": True}},
                _send_guard=lambda uid: None,
            )
            module = SimpleNamespace(
                _owner_dm=lambda chat: chat.get("owner", False),
                _owner_handle=lambda chat: "+55 31 98888-7777",
            )
            saved = whatsapp._TOKEN
            whatsapp._TOKEN = ""
            asyncio.run(whatsapp._offer_code(adapter, module, "cht_new"))
            asyncio.run(whatsapp._offer_code(adapter, module, "cht_new"))
            guarded = SimpleNamespace(_chats={}, _send_guard=lambda uid: "group")
            asyncio.run(whatsapp._offer_code(guarded, module, "cht_group"))
            whatsapp._TOKEN = "already-bound"
            asyncio.run(whatsapp._offer_code(adapter, module, "cht_later"))
            whatsapp._TOKEN = saved
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            if previous_api is None:
                os.environ.pop("PLOW_API_BASE", None)
            else:
                os.environ["PLOW_API_BASE"] = previous_api
            if previous_token is None:
                os.environ.pop("PLOW_AGENT_TOKEN", None)
            else:
                os.environ["PLOW_AGENT_TOKEN"] = previous_token
    bubbles = whatsapp.pairing_bubbles(code)
    home = [row[2]["body"] for row in posted if row[1].endswith("/cht_home/messages")]
    assert home == bubbles
    assert [row[1] for row in posted] == (
        ["https://plow.example/v1/chats/cht_home/messages"] * len(bubbles)
        + ["https://plow.example/v1/chats/cht_android/messages"] * len(bubbles)
        + ["https://plow.example/v1/chats/cht_new/messages"] * len(bubbles)
    )
    assert all(row[2]["format"] == "none" for row in posted)
    assert all("\n" not in row[2]["body"] for row in posted)


def test_pairing_code_alone_opens_whatsapp_and_a_real_text_owns_the_turn():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_pairing_turn", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    pairing = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(pairing)
    code = "142857"
    assert pairing.pairing_turn([{"text": code}], code)
    assert pairing.pairing_turn([{"text": f"  {code}  "}], code)
    assert not pairing.pairing_turn([{"text": "oi"}, {"text": code}], code)
    assert not pairing.pairing_turn([{"text": code, "media_id": "mid"}], code)
    assert not pairing.pairing_turn([{"text": code}], "")


def test_activation_code_uses_the_onboarding_chat_a_normal_reply_uses():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_rcs", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    phrase = "Set this up for me: aiworthusing.com/agent-index/zoen"
    me = {
        "signup": {"name": "Zoen", "phrase": phrase},
        "line": {"uid": "ln_p1", "provider_key": "+16503466610"},
        "chats": [
            {
                "uid": "cht_mail",
                "status": "active",
                "participants": [
                    {"type": "member", "role": "owner", "provider_type": "imessage", "provider_key": "enzo@example.com"},
                ],
            },
            {
                "uid": "cht_rcs",
                "status": "active",
                "participants": [
                    {"type": "member", "role": "owner", "provider_type": "imessage", "provider_key": "+5531999941160"},
                ],
            },
        ],
    }
    histories = {
        "cht_mail": [{"direction": "inbound", "body": "Alo"}],
        "cht_rcs": [{"direction": "inbound", "body": phrase}],
    }
    assert whatsapp.activation_chat_uids(me, histories) == ["cht_rcs"]
    posted = []

    async def fake_request(method, url, token, payload=None, extra=None):
        posted.append((method, url, payload))
        return {}

    async def fake_plow(_agent, path):
        if path.startswith("/v1/chats/cht_rcs/"):
            return {"data": histories["cht_rcs"]}
        if path.startswith("/v1/chats/cht_mail/"):
            return {"data": histories["cht_mail"]}
        return []

    whatsapp._request = fake_request
    whatsapp._plow_json = fake_plow
    previous_home = os.environ.get("HERMES_HOME")
    previous_api = os.environ.get("PLOW_API_BASE")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["PLOW_API_BASE"] = "https://plow.example"
        try:
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            code = whatsapp._pairing_code()
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            if previous_api is None:
                os.environ.pop("PLOW_API_BASE", None)
            else:
                os.environ["PLOW_API_BASE"] = previous_api
    sends = [row for row in posted if row[0] == "POST"]
    bubbles = whatsapp.pairing_bubbles(code)
    assert [row[1] for row in sends] == ["https://plow.example/v1/chats/cht_rcs/messages"] * len(bubbles)
    assert [row[2]["body"] for row in sends] == bubbles


def test_onboarding_cards_stay_inside_ten_seconds():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_budget", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    seen = {}

    def cards_sync(chat, deadline):
        seen["chat"] = chat
        seen["left"] = deadline - time.monotonic()
        return {"ok": True, "cards": ["Zoen.vcf", "Enzo.vcf"]}

    async def fake_request(method, url, token, payload=None, extra=None):
        return {}

    whatsapp._cards_sync = cards_sync
    whatsapp._request = fake_request
    previous_home = os.environ.get("HERMES_HOME")
    previous_api = os.environ.get("PLOW_API_BASE")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["PLOW_API_BASE"] = "https://api.plow.co"
        try:
            asyncio.run(whatsapp._announce_code("agt_test", "cht_home", "142857"))
            asyncio.run(whatsapp._attach_cards("cht_home", time.monotonic() - 1))
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            if previous_api is None:
                os.environ.pop("PLOW_API_BASE", None)
            else:
                os.environ["PLOW_API_BASE"] = previous_api
    assert seen["chat"] == "cht_home"
    assert 0 < seen["left"] <= whatsapp.ONBOARD_SECONDS


def test_pairing_code_is_sent_without_the_owner_texting_first():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_open", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    previous_home = os.environ.get("HERMES_HOME")
    previous_api = os.environ.get("PLOW_API_BASE")
    posted = []

    async def fake_request(method, url, token, payload=None, extra=None):
        posted.append((method, url, payload))
        return {"uid": "cht_opened", "created": True}

    async def fake_plow(_agent, path):
        assert path == "/v1/contacts"
        return [{"role": "owner", "provider_key": "+55 31 98888-7777"}, {"role": "member", "provider_key": "+15555550100"}]

    whatsapp._request = fake_request
    whatsapp._plow_json = fake_plow
    me = {"line": {"uid": "ln_p4", "provider_key": "+16503156415"}, "chats": []}
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["PLOW_API_BASE"] = "https://plow.example"
        try:
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            code = whatsapp._pairing_code()
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            whatsapp._forget_code()
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            replacement = whatsapp._pairing_code()
            asyncio.run(whatsapp._push_pairing("agt_test", me))
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            if previous_api is None:
                os.environ.pop("PLOW_API_BASE", None)
            else:
                os.environ["PLOW_API_BASE"] = previous_api
    assert [(row[0], row[1]) for row in posted] == [
        ("POST", "https://plow.example/v1/chats"),
        ("POST", "https://plow.example/v1/chats"),
    ]
    opened = posted[0][2]
    assert opened["line_uid"] == "ln_p4"
    assert opened["members"] == ["+5531988887777"]
    assert code in opened["body"]
    assert opened["idempotency_key"] == f"zoen-wa-{code}-5531988887777"
    assert code != replacement
    assert replacement in posted[1][2]["body"]


def test_pairing_code_opens_the_owner_email_when_nobody_texted():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_email", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    previous_home = os.environ.get("HERMES_HOME")
    previous_api = os.environ.get("PLOW_API_BASE")
    posted = []

    async def fake_request(method, url, token, payload=None, extra=None):
        posted.append((method, url, payload))
        return {"uid": "cht_mail_opened", "created": True}

    async def fake_plow(_agent, path):
        assert path == "/v1/contacts"
        return [{"role": "owner", "provider_key": "enzotironi.dev@gmail.com"}]

    whatsapp._request = fake_request
    whatsapp._plow_json = fake_plow
    me = {"agent": {"uid": "d" * 32}, "line": {"uid": "ln_p2", "provider_key": "+16503156335"}, "chats": []}
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["PLOW_API_BASE"] = "https://plow.example"
        try:
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            code = whatsapp._pairing_code()
            asyncio.run(whatsapp._push_pairing("agt_test", me))
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            if previous_api is None:
                os.environ.pop("PLOW_API_BASE", None)
            else:
                os.environ["PLOW_API_BASE"] = previous_api
    sends = [row for row in posted if row[0] == "POST"]
    assert len(sends) == 1
    opened = sends[0][2]
    assert opened["line_uid"] == "ln_p2"
    assert opened["members"] == ["enzotironi.dev@gmail.com"]
    assert code in opened["body"]
    assert opened["idempotency_key"] == f"zoen-wa-{code}-enzotironi.dev@gmail.com"


def test_pairing_code_uses_the_mailbox_when_the_phone_line_has_no_thread():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_mailbox", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    previous_home = os.environ.get("HERMES_HOME")
    previous_api = os.environ.get("PLOW_API_BASE")
    posted = []

    async def fake_request(method, url, token, payload=None, extra=None):
        posted.append((method, url, payload))
        if url.endswith("/v1/chats"):
            raise RuntimeError(
                "whatsapp_http_404_{'code': 'line_not_found', 'message': \"line 'ln_p2' not found.\"}"
            )
        return {"id": "mail_sent"}

    async def fake_plow(_agent, path):
        if path == "/v1/contacts":
            return [{"role": "owner", "provider_key": "enzotironi.dev@gmail.com"}]
        if path == "/v1/lines":
            return {"data": [
                {"uid": "ln_p2", "provider_type": "imessage", "display_name": "Aspen"},
                {"uid": "ln_e_box", "provider_type": "email", "display_name": "Aspen"},
            ]}
        raise AssertionError(path)

    whatsapp._request = fake_request
    whatsapp._plow_json = fake_plow
    me = {
        "agent": {"uid": "d" * 32},
        "line": {"uid": "ln_p2", "provider_key": "+16503156335", "display_name": "Aspen"},
        "chats": [],
    }
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["PLOW_API_BASE"] = "https://plow.example"
        try:
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            code = whatsapp._pairing_code()
            asyncio.run(whatsapp._push_pairing("agt_test", me))
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            if previous_api is None:
                os.environ.pop("PLOW_API_BASE", None)
            else:
                os.environ["PLOW_API_BASE"] = previous_api
    mailed = [row for row in posted if row[1].endswith("/messages")]
    assert len(mailed) == 1
    assert mailed[0][1] == "https://plow.example/v1/email-lines/ln_e_box/messages"
    assert mailed[0][2]["to"] == ["enzotironi.dev@gmail.com"]
    assert code in mailed[0][2]["body"]


def test_reused_line_volume_sends_the_code_once_for_the_new_agent():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_reuse", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    previous_home = os.environ.get("HERMES_HOME")
    previous_api = os.environ.get("PLOW_API_BASE")
    posted = []

    async def fake_request(method, url, token, payload=None, extra=None):
        posted.append((method, url, payload))
        return {}

    whatsapp._request = fake_request
    previous = "a" * 32
    current = "b" * 32
    me = {
        "agent": {"uid": current},
        "line": {"uid": "ln_p5", "provider_key": "+16503156604"},
        "chats": [{
            "uid": "cht_alder",
            "status": "active",
            "participants": [
                {"type": "agent", "relationship": "self"},
                {"type": "member", "role": "owner", "provider_type": "imessage", "provider_key": "+55 31 98888-7777"},
            ],
        }],
    }
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["PLOW_API_BASE"] = "https://plow.example"
        try:
            whatsapp._write_install(previous)
            whatsapp._write_token("T" * 43)
            whatsapp._claim_chat("cht_alder")
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            assert whatsapp._read_install() == current
            assert whatsapp._read_token() == ""
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            if previous_api is None:
                os.environ.pop("PLOW_API_BASE", None)
            else:
                os.environ["PLOW_API_BASE"] = previous_api
    assert [row[1] for row in posted if row[0] == "POST"] == [
        "https://plow.example/v1/chats/cht_alder/messages",
    ] * len(whatsapp.pairing_bubbles("000000"))


def test_same_agent_texts_the_code_once_when_the_image_changes():
    spec_wa = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_image", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    whatsapp = importlib.util.module_from_spec(spec_wa)
    spec_wa.loader.exec_module(whatsapp)
    previous_home = os.environ.get("HERMES_HOME")
    previous_api = os.environ.get("PLOW_API_BASE")
    previous_image = os.environ.get("ZOEN_IMAGE_ID")
    posted = []

    async def fake_request(method, url, token, payload=None, extra=None):
        posted.append((method, url, payload))
        return {}

    whatsapp._request = fake_request
    current = "c" * 32
    me = {
        "agent": {"uid": current},
        "line": {"uid": "ln_p5", "provider_key": "+16503156604"},
        "chats": [{
            "uid": "cht_alder",
            "status": "active",
            "participants": [
                {"type": "agent", "relationship": "self"},
                {"type": "member", "role": "owner", "provider_type": "imessage", "provider_key": "+55 31 98888-7777"},
            ],
        }],
    }
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        os.environ["PLOW_API_BASE"] = "https://plow.example"
        os.environ["ZOEN_IMAGE_ID"] = "image-new-0001"
        try:
            os.makedirs(os.path.dirname(whatsapp._install_path()), mode=0o700, exist_ok=True)
            with open(whatsapp._install_path(), "w", encoding="utf-8") as handle:
                handle.write(current + "\nimage-old-0001\n")
            whatsapp._write_token("T" * 43)
            whatsapp._claim_chat("cht_alder")
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            asyncio.run(whatsapp._push_pairing("agt_test", me))
            assert whatsapp._read_install() == current
            assert whatsapp._read_image() == "image-new-0001"
            assert whatsapp._read_token() == "T" * 43
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            if previous_api is None:
                os.environ.pop("PLOW_API_BASE", None)
            else:
                os.environ["PLOW_API_BASE"] = previous_api
            if previous_image is None:
                os.environ.pop("ZOEN_IMAGE_ID", None)
            else:
                os.environ["ZOEN_IMAGE_ID"] = previous_image
    assert [row[1] for row in posted if row[0] == "POST"] == [
        "https://plow.example/v1/chats/cht_alder/messages",
    ] * len(whatsapp.pairing_bubbles("000000"))


def test_whatsapp_bubbles_quote_and_files_stay_on_whatsapp():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    sent = []
    media = []

    async def deliver(payload):
        sent.append(payload)
        return True

    async def send_media(spec):
        media.append(spec)
        return True

    quiet.WHATSAPP_DELIVER = deliver
    quiet.WHATSAPP_MEDIA = send_media
    token = quiet.WHATSAPP.set({"to": "5511999999999", "message_id": "wamid.1"})
    try:
        result = asyncio.run(box.send_sequence({"items": [
            {"type": "text", "body": "oi", "reply_to": "wamid.1"},
            {"type": "pause", "seconds": 0},
            {"type": "text", "body": "segunda"},
            {"type": "text", "body": "MEDIA:/tmp/shot.png"},
            {"type": "text", "body": "VOICE:/tmp/note.m4a"},
        ]}, {"chat_uid": "cht_x"}))
    finally:
        quiet.WHATSAPP.reset(token)
        quiet.WHATSAPP_DELIVER = None
        quiet.WHATSAPP_MEDIA = None
    assert result["success"] is True
    assert sent == [{"text": "oi", "reply_to": "wamid.1"}, "segunda"]
    assert media == [
        {"path": "/tmp/shot.png", "voice": False, "reply_to": ""},
        {"path": "/tmp/note.m4a", "voice": True, "reply_to": ""},
    ]
    assert box.posted == []


def test_whatsapp_line_break_is_its_own_bubble():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    sent = []

    async def deliver(payload):
        sent.append(payload)
        return True

    quiet.WHATSAPP_DELIVER = deliver
    token = quiet.WHATSAPP.set({"to": "5511999999999", "message_id": "wamid.1"})
    try:
        result = asyncio.run(box.send_sequence({"items": [
            {"type": "text", "body": "consigo sim, do rabisco ao visual bem acabado\nme diz o que você quer ver", "reply_to": "wamid.1"},
        ]}, {"chat_uid": "cht_x"}))
    finally:
        quiet.WHATSAPP.reset(token)
        quiet.WHATSAPP_DELIVER = None
    assert result["success"] is True
    assert sent == [
        {"text": "consigo sim, do rabisco ao visual bem acabado", "reply_to": "wamid.1"},
        "me diz o que você quer ver",
    ]
    assert box.posted == []


def test_whatsapp_uncertain_send_is_not_repeated():
    spec = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_once", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._RECENT.clear()
    module._TOKEN = "a" * 43
    calls = []

    async def flaky(method, url, token, body=None):
        calls.append(body["text"])
        if len(calls) == 1:
            raise module._Uncertain()
        raise AssertionError("retried an uncertain bubble")

    module._request = flaky
    assert asyncio.run(module._send("https://relay.example", {"text": "oi", "to": "5511999999999"})) is True
    assert asyncio.run(module._send("https://relay.example", {"text": "oi", "to": "5511999999999"})) is True
    assert calls == ["oi"]


def test_whatsapp_reaction_is_the_agents_tapback_not_a_second_model():
    source = (ROOT / "image/plugins/zoen-face/whatsapp.py").read_text()
    assert "_react(" not in source
    assert "reaction.emoji" in source
    assert "skill kapso" in source


def test_imessage_quote_field_does_not_reach_plow():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    result = asyncio.run(box.send_sequence(
        {"items": [{"type": "text", "body": "oi", "reply_to": "wamid.1"}]},
        {"chat_uid": "cht_x"},
    ))
    assert result["success"] is True
    assert box.posted == [("sequence", {"items": [{"type": "text", "body": "oi"}]})]


def test_whatsapp_turn_stays_in_the_session():
    source = (ROOT / "image/plugins/zoen-face/whatsapp.py").read_text()
    assert "event.internal = False" in source
    assert "event.internal = True" not in source
    spec = importlib.util.spec_from_file_location(
        "zoen_face_whatsapp_prompt", ROOT / "image/plugins/zoen-face/whatsapp.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt = module._prompt("wamid.1")
    assert "history" in prompt
    assert "reaction.emoji" in prompt
    assert "context.message_id" in prompt
    assert "skill kapso" in prompt
    first = module._prompt("wamid.1", first=True)
    assert "first-contact" in first
    assert "Do not greet again" not in first


def test_whatsapp_reply_stays_off_imessage():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    sent = []

    async def deliver(text):
        sent.append(text)
        return True

    quiet.WHATSAPP_DELIVER = deliver
    token = quiet.WHATSAPP.set({"to": "5511999999999"})
    try:
        result = asyncio.run(box.send_sequence({"items": [{"type": "text", "body": "oi"}]}, {"chat_uid": "cht_x"}))
    finally:
        quiet.WHATSAPP.reset(token)
        quiet.WHATSAPP_DELIVER = None
    assert result["success"] is True
    assert sent == ["oi"]
    assert box.posted == []


def test_send_sequence_still_runs():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    args = {"items": [{"type": "text", "body": "shipped"}]}
    result = asyncio.run(box.send_sequence(args, {"chat_uid": "cht_x"}))
    assert result["success"] is True
    assert box.posted == [("sequence", args)]


def test_native_final_media_and_typing_are_preserved_status_chatter_is_dropped():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    asyncio.run(box.send_image_file("cht_x", "/tmp/demo.png"))
    asyncio.run(box.send_or_update_status("cht_x", "working", "compiling"))
    asyncio.run(box.send_typing("cht_x"))
    assert box.posted == [("image", "/tmp/demo.png"), ("typing", "cht_x")]


def test_media_sequence_uploads_file_instead_of_the_path():
    Adapter = _adapter()
    with tempfile.TemporaryDirectory() as folder:
        png = Path(folder) / "home.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        saved = quiet._MEDIA_ROOTS
        quiet._MEDIA_ROOTS = (Path(folder),)
        try:
            quiet.silence(Adapter)
            box = Adapter()
            args = {
                "items": [
                    {"type": "text", "body": f"MEDIA:{png}"},
                    {"type": "text", "body": "shipped"},
                ]
            }
            asyncio.run(box.send_sequence(args, {"chat_uid": "cht_x"}))
        finally:
            quiet._MEDIA_ROOTS = saved
    assert box.posted == [
        ("file", str(png.resolve())),
        ("sequence", {"items": [{"type": "text", "body": "shipped"}]}),
    ]
    assert not any("MEDIA:" in str(row) for row in box.posted)


def test_media_outside_workspace_is_not_posted_as_text():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    args = {
        "items": [
            {
                "type": "text",
                "body": "MEDIA:/etc/passwd",
            }
        ]
    }
    quiet.log.disabled = True
    try:
        result = asyncio.run(box.send_sequence(args, {"chat_uid": "cht_x"}))
    finally:
        quiet.log.disabled = False
    assert box.posted == []
    assert result["success"] is False


def test_silence_is_idempotent():
    Adapter = _adapter()
    quiet.silence(Adapter)
    first = Adapter.send
    quiet.silence(Adapter)
    assert Adapter.send is first
    box = Adapter()
    asyncio.run(box.send("cht_x", "Hello leftover"))
    assert box.posted == []


def test_voice_sequence_uses_native_send_voice():
    Adapter = _adapter()
    with tempfile.TemporaryDirectory() as folder:
        m4a = Path(folder) / "note.m4a"
        m4a.write_bytes(b"ftypM4A " + b"\x00" * 8)
        saved = quiet._MEDIA_ROOTS
        quiet._MEDIA_ROOTS = (Path(folder),)
        try:
            quiet.silence(Adapter)
            box = Adapter()
            args = {
                "items": [
                    {"type": "text", "body": f"VOICE:{m4a}"},
                    {"type": "text", "body": "shipped"},
                ]
            }
            asyncio.run(box.send_sequence(args, {"chat_uid": "cht_x"}))
        finally:
            quiet._MEDIA_ROOTS = saved
    assert box.posted == [
        ("voice", str(m4a.resolve())),
        ("sequence", {"items": [{"type": "text", "body": "shipped"}]}),
    ]


def test_native_final_voice_is_preserved():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    asyncio.run(box.send_voice("cht_x", "/tmp/note.m4a"))
    assert box.posted == [("voice", "/tmp/note.m4a")]


def test_silence_finds_adapter_in_sys_modules():
    import sys
    import types

    Adapter = _adapter()
    Adapter.__name__ = "PlowChatAdapter"
    mod = types.ModuleType("zoen_fake_plow_chat")
    mod.PlowChatAdapter = Adapter
    sys.modules["zoen_fake_plow_chat"] = mod
    try:
        quiet.silence_plow_adapter()
        box = Adapter()
        asyncio.run(box.send("cht_x", "leftover"))
        assert box.posted == []
    finally:
        del sys.modules["zoen_fake_plow_chat"]


def test_missing_adapter_does_not_raise():
    quiet.log.disabled = True
    try:
        quiet.silence_plow_adapter()
    finally:
        quiet.log.disabled = False


def test_failed_media_does_not_become_a_successful_text_delivery(tmp_path):
    Adapter = _adapter()

    async def failed(self, *args, **kwargs):
        self.posted.append(("failed_file", args))
        return SimpleNamespace(success=False, error="network timeout")

    Adapter._send_attachment = failed
    saved = quiet._MEDIA_ROOTS
    quiet._MEDIA_ROOTS = (tmp_path,)
    path = tmp_path / "test.png"
    path.write_bytes(b"image fixture")
    try:
        quiet.silence(Adapter)
        box = Adapter()
        result = asyncio.run(box.send_sequence({"items": [
            {"type": "text", "body": f"MEDIA:{path}"},
            {"type": "text", "body": "done"},
        ]}, {"chat_uid": "cht_x"}))
        assert result["success"] is False
        assert result["failure"]["status"] == "rejected"
        assert result["failure"]["retryable"] is False
        assert len(box.posted) == 1
    finally:
        quiet._MEDIA_ROOTS = saved


def test_claim_identity_replaces_the_line_name():
    def original(prompt, name, identity):
        who = f"You are {name}, a Plow assistant" if name else "You are a Plow assistant."
        return f"{who} {prompt}"

    module = SimpleNamespace(
        _with_identity=original,
        _plow_facts=lambda _identity: "facts.",
    )
    quiet.claim_identity(module)
    quiet.claim_identity(module)
    text = module._with_identity("keep going", "Spruce", {})
    assert text.startswith("You are Zoen")
    assert "Spruce" not in text
    assert "You are a Plow assistant" not in text
    assert "facts." in text
    assert text.endswith("keep going")


def test_claim_identity_skips_modules_without_the_seam():
    module = SimpleNamespace()
    quiet.claim_identity(module)
    assert not hasattr(module, "_with_identity")


def test_seed_soul_is_zoen_not_a_plow_assistant():
    soul = (ROOT / "runtime" / "SOUL.md").read_text()
    persona = (ROOT / "runtime" / "persona.md").read_text()
    assert soul.lstrip().startswith("# Zoen")
    assert persona.lstrip().startswith("# Who you are")
    assert soul.split("\n", 1)[1] == persona.split("\n", 1)[1]
    assert "You are **Zoen**" in soul
    assert "https://tryzoen.com" in soul
    assert "add you to an iMessage group" in soul
    assert "You are a Plow assistant" not in soul
    assert "mention /help" in soul.lower()
    assert "zoen_connections" in soul
    assert "zoen_imessage" in soul
    assert "Anything you make for them is shown in this chat" in persona
    assert "catalog" in soul


def test_persona_route_index_names_playbooks_and_skills():
    persona = (ROOT / "runtime" / "persona.md").read_text()
    assert "# Route" in persona
    for needle in (
        "context.py dump",
        "zoen_imessage",
        "latest **human**",
        "zoen_connections",
        "catalog",
        "treg",
        "monid",
        "google-workspace",
        "index.md",
        "personal.md",
        "connections.md",
        "feature.md",
        "bug-fix.md",
        "investigation.md",
        "spec.md",
        "cards.md",
        "opening-a-pr.md",
        "kit.md",
        "models.md",
        "skill_view",
        "`hours`",
        "`how`",
        "`why`",
        "`architect`",
        "`arena`",
        "`interrogate`",
        "`swarm`",
        "`tdd`",
        "`prove`",
        "`review`",
        "`blast-radius`",
        "`babysit`",
        "`merge`",
        "`figure-it-out`",
        "`find-skills`",
        "`floor`",
        "`kapso`",
    ):
        assert needle in persona, needle
    index = (ROOT / "skills" / "zoen" / "playbooks" / "index.md").read_text()
    for heading in ("## Use cases", "## Playbooks", "## Connectors"):
        assert heading in index, heading
    playbooks = ROOT / "skills" / "zoen" / "playbooks"
    for path in playbooks.glob("*.md"):
        if path.name == "index.md":
            continue
        assert path.name in index, path.name
    for name in ("treg", "monid", "notion", "google", "slack", "kiwi"):
        assert f"`{name}`" in index, name
    for source in (
        "https://treg.to/use-cases",
        "https://treg.to/workflows",
        "https://poke.com/recipes",
        "https://assistantbenchmark.com/use-cases",
        "monid_discover",
    ):
        assert source in index, source


if __name__ == "__main__":
    test_normal_final_is_dropped()
    test_contract_renames_send_and_forbids_leftover()
    test_leftover_credits_error_becomes_the_dashboard_bubble()
    test_contract_moves_scoped_factory_send_to_zoen_imessage()
    test_retired_hello_http_post_is_dropped()
    test_retired_hello_is_dropped()
    test_whatsapp_owner_phone_is_the_handle_digits()
    test_whatsapp_poll_starts_when_the_line_connects()
    test_whatsapp_credits_follow_the_inbound_and_imessage_stays_on_imessage()
    test_agent_secret_is_stable_for_the_volume()
    test_pairing_code_stays_on_the_volume_and_opens_whatsapp()
    test_pairing_code_reaches_every_phone_chat()
    test_pairing_code_alone_opens_whatsapp_and_a_real_text_owns_the_turn()
    test_activation_code_uses_the_onboarding_chat_a_normal_reply_uses()
    test_onboarding_cards_stay_inside_ten_seconds()
    test_pairing_code_is_sent_without_the_owner_texting_first()
    test_pairing_code_opens_the_owner_email_when_nobody_texted()
    test_pairing_code_uses_the_mailbox_when_the_phone_line_has_no_thread()
    test_reused_line_volume_sends_the_code_once_for_the_new_agent()
    test_same_agent_texts_the_code_once_when_the_image_changes()
    test_whatsapp_bubbles_quote_and_files_stay_on_whatsapp()
    test_whatsapp_line_break_is_its_own_bubble()
    test_whatsapp_uncertain_send_is_not_repeated()
    test_whatsapp_reaction_is_the_agents_tapback_not_a_second_model()
    test_imessage_quote_field_does_not_reach_plow()
    test_whatsapp_turn_stays_in_the_session()
    test_whatsapp_reply_stays_off_imessage()
    test_send_sequence_still_runs()
    test_native_final_media_and_typing_are_preserved_status_chatter_is_dropped()
    test_media_sequence_uploads_file_instead_of_the_path()
    test_media_outside_workspace_is_not_posted_as_text()
    test_silence_is_idempotent()
    test_voice_sequence_uses_native_send_voice()
    test_native_final_voice_is_preserved()
    test_silence_finds_adapter_in_sys_modules()
    test_missing_adapter_does_not_raise()
    test_claim_identity_replaces_the_line_name()
    test_claim_identity_skips_modules_without_the_seam()
    test_seed_soul_is_zoen_not_a_plow_assistant()
    test_persona_route_index_names_playbooks_and_skills()
    print("ok")
