#!/usr/bin/env python3
"""WhatsApp line id and relay body stay off the iMessage adapter."""

import importlib.util
import os
import sys
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "whatsapp_line", ROOT / "image/plugins/zoen-face/whatsapp_line.py"
)
line = importlib.util.module_from_spec(spec)
sys.modules["whatsapp_line"] = line
spec.loader.exec_module(line)


def test_whatsapp_text_steers_the_running_session():
    import asyncio

    class Outcome:
        steered = True

    class Runner:
        def __init__(self):
            self.mode = None

        def _peek_session_state(self, session_key):
            assert session_key == "agent:main:whatsapp:dm:5537999999999"
            return None

        async def _resolve_busy_steer_or_redirect(self, event, session_key, mode, agent):
            self.mode = mode
            assert event.text == "espera, muda o tom"
            assert agent is None
            return Outcome()

    runner = Runner()
    event = type("Event", (), {"text": "espera, muda o tom", "media_urls": None})()

    async def gateway(event, session_key):
        return False

    assert asyncio.run(line.steer_followup(
        gateway, runner, event, "agent:main:whatsapp:dm:5537999999999"
    ))
    assert runner.mode == "steer"


def test_handled_busy_event_is_not_steered_again():
    import asyncio

    class Runner:
        def _resolve_busy_steer_or_redirect(self, *args):
            raise AssertionError("gateway already handled this event")

    async def gateway(event, session_key):
        return True

    event = type("Event", (), {"text": "sim", "media_urls": None})()
    assert asyncio.run(line.steer_followup(gateway, Runner(), event, "s"))


def test_unstuck_steer_falls_through_to_the_queue():
    import asyncio

    class Outcome:
        steered = False

    class Runner:
        def _peek_session_state(self, session_key):
            return None

        async def _resolve_busy_steer_or_redirect(self, event, session_key, mode, agent):
            return Outcome()

    async def gateway(event, session_key):
        return False

    event = type("Event", (), {"text": "oi", "media_urls": ["a.jpg"]})()
    assert not asyncio.run(line.steer_followup(gateway, Runner(), event, "s"))
    event = type("Event", (), {"text": "oi", "media_urls": None})()
    assert not asyncio.run(line.steer_followup(gateway, Runner(), event, "s"))


def test_hermes_session_keeps_the_phone():
    burst = line.burst_from_relay({
        "id": "wamid.IN",
        "text": "oi",
        "to": "+55 37 99999-9999",
    })
    assert burst.line_id == "whatsapp:5537999999999"
    assert line.session_chat_id(burst) == "5537999999999"
    assert ":" not in line.session_chat_id(burst)


def test_burst_uses_whatsapp_line_id():
    burst = line.burst_from_relay({
        "id": "wamid.ABC",
        "text": "e esse?",
        "to": "+55 37 99999-9999",
        "reply_to": "wamid.OLD",
        "reply_text": "deploy falhou",
    })
    assert burst.line_id == "whatsapp:5537999999999"
    assert not burst.line_id.startswith("cht_")
    assert burst.pointed == line.Bubble(id="wamid.OLD", text="deploy falhou")
    assert burst.message_id == "wamid.ABC"


def test_text_delivery_matches_relay_send():
    address = line.Address(to="5537999999999")
    body = line.relay_body(address, line.TextDelivery(body="rollback feito", reply_to="wamid.OLD"))
    assert body == {
        "to": "5537999999999",
        "text": "rollback feito",
        "reply_to": "wamid.OLD",
    }


def test_reaction_delivery_matches_the_relay_object():
    address = line.Address(to="5537999999999")
    body = line.relay_body(address, line.ReactionDelivery(message_id="wamid.OLD", kind="love"))
    assert body == {
        "to": "5537999999999",
        "reaction": {"message_id": "wamid.OLD", "type": "love"},
    }


def test_poll_stays_near_and_drops_a_rejected_session():
    assert [line.poll_pause(n) for n in range(0, 6)] == [1, 2, 5, 5, 5, 5]

    class Transport:
        token = "stale"

    transport = Transport()
    denied = HTTPError("https://relay.example/whatsapp/inbox", 403, "unauthorized", hdrs=None, fp=None)
    assert line.absorb_poll_error(4, denied, transport) == 0
    assert transport.token == ""
    assert line.absorb_poll_error(1, TimeoutError(), transport) == 2


def test_register_does_not_replace_plow_chat_methods():
    class Plow:
        async def _on_message(self, message, chat):
            return None

    original = Plow._on_message
    seen = {}

    class Ctx:
        def register_platform(self, **kwargs):
            seen.update(kwargs)

    os.environ["ZOEN_OAUTH_RELAY_URL"] = "https://relay.example"
    try:
        line.register_line(Ctx())
        assert seen["check_fn"]() is True
    finally:
        os.environ.pop("ZOEN_OAUTH_RELAY_URL", None)

    assert Plow._on_message is original
    assert seen["name"] == "zoen-whatsapp"
    assert seen["required_env"] == ["ZOEN_OAUTH_RELAY_URL"]
    assert seen["check_fn"]() is False


def test_send_posts_relay_body():
    import asyncio

    posted = []

    class Transport:
        async def post(self, url, body):
            posted.append((url, body))

    adapter = line.WhatsAppLine("https://relay.example", Transport())

    async def run():
        await adapter.send(
            "whatsapp:5537999999999",
            "oi",
            reply_to="wamid.ABC",
        )

    asyncio.run(run())
    assert posted == [(
        "https://relay.example/whatsapp/send",
        {"to": "5537999999999", "text": "oi", "reply_to": "wamid.ABC"},
    )]


def test_poll_once_acks_without_touching_an_adapter_class():
    import asyncio

    calls = []

    class Transport:
        async def get(self, url):
            calls.append(("get", url))
            return {"messages": [{
                "id": "wamid.IN",
                "text": "oi",
                "to": "5537999999999",
            }]}

        async def post(self, url, body):
            calls.append(("post", url, body))

    adapter = line.WhatsAppLine("https://relay.example/", Transport())

    async def handler(burst):
        return burst

    adapter.handle_message = handler
    bursts = asyncio.run(adapter.poll_once())
    assert [burst.line_id for burst in bursts] == ["whatsapp:5537999999999"]
    assert calls == [
        ("get", "https://relay.example/whatsapp/inbox"),
        ("post", "https://relay.example/whatsapp/inbox/ack", {"ids": ["wamid.IN"]}),
    ]


def test_an_authorization_link_is_a_whatsapp_button():
    url = "https://auth.example/oauth?state=abc"
    cards = line.authorization_cards(
        "treg",
        "Pending authorization. This link expires in 15 minutes.\n"
        f"Authorization URL:\n{url}",
    )
    assert cards == [{
        "text": "Treg\nO link expira em 15 minutos.",
        "url": url,
        "label": "Autorizar",
    }]
    assert line.authorization_cards("google", "Google identity verified: owner@example.com.") == []
    body = line.relay_body(
        line.Address(to="5537999999999"),
        line.ButtonDelivery(body=cards[0]["text"], url=url, label="Autorizar"),
    )
    assert body["button"] == {"url": url, "label": "Autorizar"}
    assert "http" not in body["text"]


def test_poll_once_acks_a_repeated_text_without_a_second_turn():
    import asyncio

    calls = []
    seen = []

    class Transport:
        async def get(self, url):
            return {"messages": [
                {"id": "wamid.A", "text": "chegou", "to": "5537999999999"},
                {"id": "wamid.B", "text": "chegou", "to": "5537999999999"},
            ]}

        async def post(self, url, body):
            calls.append(body)

    adapter = line.WhatsAppLine("https://relay.example/", Transport())

    async def handler(burst):
        seen.append(burst.message_id)
        return burst

    adapter.handle_message = handler
    bursts = asyncio.run(adapter.poll_once())
    assert [burst.message_id for burst in bursts] == ["wamid.A"]
    assert seen == ["wamid.A"]
    assert calls == [{"ids": ["wamid.A", "wamid.B"]}]


def test_poll_once_holds_the_bubble_until_a_handler_accepts_it():
    import asyncio

    calls = []

    class Transport:
        async def get(self, url):
            calls.append(("get", url))
            return {"messages": [{
                "id": "wamid.IN",
                "text": "oi",
                "to": "5537999999999",
            }]}

        async def post(self, url, body):
            calls.append(("post", url, body))

    adapter = line.WhatsAppLine("https://relay.example/", Transport())
    bursts = asyncio.run(adapter.poll_once())
    assert bursts == []
    assert calls == [("get", "https://relay.example/whatsapp/inbox")]


def test_connect_starts_the_poll_without_replacing_plow_chat():
    import asyncio

    class Plow:
        async def _on_message(self, message, chat):
            return None

    original = Plow._on_message
    started = asyncio.Event()

    class Transport:
        async def get(self, url):
            started.set()
            await asyncio.Event().wait()

        async def post(self, url, body):
            return {}

    adapter = line.WhatsAppLine("https://relay.example", Transport())

    async def run():
        assert await adapter.connect() is True
        await asyncio.wait_for(started.wait(), 1)
        assert adapter._task is not None
        await adapter.disconnect()
        assert adapter._task is None

    asyncio.run(run())
    assert Plow._on_message is original


def test_owner_bubble_stays_on_the_whatsapp_line_after_accept_returns():
    import asyncio

    posted = []

    class Transport:
        async def post(self, url, body):
            posted.append((url, body))

    adapter = line.WhatsAppLine("https://relay.example", Transport())

    seen = {}

    async def later():
        seen["line"] = line.LINE.get()
        await adapter.post_owner("oi")

    async def handler(burst):
        adapter.later = asyncio.get_running_loop().create_task(later())
        return True

    adapter.handle_message = handler

    async def run():
        accepted = await adapter.accept({
            "id": "wamid.IN",
            "text": "e esse?",
            "to": "+55 37 99999-9999",
        })
        assert line.LINE.get() == ""
        await adapter.later
        return accepted

    accepted = asyncio.run(run())
    assert seen["line"] == "whatsapp:5537999999999"
    assert accepted.line_id == "whatsapp:5537999999999"
    assert posted == [(
        "https://relay.example/whatsapp/send",
        {"to": "5537999999999", "text": "oi"},
    )]


def test_owner_file_posts_relay_media():
    import asyncio
    import tempfile
    from pathlib import Path

    posted = []

    class Transport:
        async def post(self, url, body):
            posted.append(body)

    adapter = line.WhatsAppLine("https://relay.example", Transport())
    adapter.reply_target = {"to": "5537999999999", "message_id": "wamid.IN"}
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "shot.png"
        path.write_bytes(b"png")
        assert asyncio.run(adapter.post_media({"path": str(path), "reply_to": "wamid.IN"})) is True
    body = posted[0]
    assert body["to"] == "5537999999999"
    assert body["reply_to"] == "wamid.IN"
    assert body["media"]["mime"] == "image/png"
    assert body["media"]["name"] == "shot.png"
    assert body["media"]["voice"] is False


def test_bound_phone_admits_only_that_whatsapp_line():
    assert line.line_is_bound("whatsapp:5537999999999", "+55 37 99999-9999") is True
    assert line.line_is_bound("whatsapp:5537999999999", "5511999999999") is False
    assert line.line_is_bound("cht_home", "5537999999999") is False
    assert line.line_is_bound("whatsapp:5537999999999", "") is False


def test_admits_the_bound_whatsapp_line_or_the_owner_dm():
    import asyncio
    import types

    pkg = types.ModuleType("zoen_face_admits")
    pkg.__path__ = [str(ROOT / "image/plugins/zoen-face")]
    pkg.__package__ = "zoen_face_admits"
    sys.modules["zoen_face_admits"] = pkg
    connect = types.ModuleType("connect")
    connect.connection = lambda *args, **kwargs: None
    sys.modules["connect"] = connect
    quiet_stub = types.ModuleType("zoen_face_admits.quiet")
    quiet_stub._read_whatsapp_stamp = lambda: {}
    sys.modules["zoen_face_admits.quiet"] = quiet_stub
    sys.modules["zoen_face_admits.whatsapp_line"] = line
    whatsapp = types.ModuleType("zoen_face_admits.whatsapp")
    whatsapp.phone_from_identity = lambda me: "5537999999999" if me.get("ok") else ""
    sys.modules["zoen_face_admits.whatsapp"] = whatsapp
    spec_connections = importlib.util.spec_from_file_location(
        "zoen_face_admits.connections",
        ROOT / "image/plugins/zoen-face/connections.py",
    )
    connections = importlib.util.module_from_spec(spec_connections)
    sys.modules["zoen_face_admits.connections"] = connections
    spec_connections.loader.exec_module(connections)

    class Adapter:
        def __init__(self):
            self._chats = {"cht_home": {"owner": True}}

        async def _tool_json(self, method, path):
            assert (method, path) == ("GET", "/v1/agents/me")
            return {"ok": True}

        def _send_guard(self, chat):
            return None if chat == "cht_home" else "blocked"

    class Module:
        def _owner_dm(self, chat):
            return bool(chat.get("owner"))

    async def run():
        bound = line.LINE.set("whatsapp:5537999999999")
        try:
            assert await connections.admits(Adapter(), Module(), "ignored") is True
            assert await connections.admits(
                Adapter(), Module(), "ignored", "whatsapp:5511999999999",
            ) is False
        finally:
            line.LINE.reset(bound)
        assert await connections.admits(Adapter(), Module(), "cht_home") is True
        assert await connections.admits(Adapter(), Module(), "cht_other") is False
        assert await connections.admits(
            Adapter(), Module(), "whatsapp:5537999999999",
        ) is True
        assert await connections.admits(Adapter(), Module(), "ignored") is False

    asyncio.run(run())


def test_relay_binding_authorizes_every_install():
    import ast

    tree = ast.parse((ROOT / "image/plugins/zoen-face/whatsapp_line.py").read_text())
    returns_true = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "authorization_is_upstream":
            continue
        returns_true = any(
            isinstance(item, ast.Return) and isinstance(item.value, ast.Constant) and item.value.value is True
            for item in ast.walk(node)
        )
    assert returns_true
    assert "source.delivered_via_upstream_relay = True" in (ROOT / "image/plugins/zoen-face/whatsapp_line.py").read_text()


def test_relay_client_identifies_itself():
    seen = {}

    class Result:
        def read(self):
            return b'{"messages": []}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(request, timeout):
        del timeout
        seen["agent"] = request.get_header("User-agent")
        return Result()

    original = line.urlopen
    line.urlopen = fake_open
    try:
        transport = line.RelayTransport()
        transport.token = "t" * 43
        transport._call("GET", "https://relay.example/whatsapp/inbox", None)
    finally:
        line.urlopen = original
    assert seen["agent"] == "Zoen"


def test_credits_failure_is_the_ready_notice_once_per_message():
    import asyncio
    import tempfile

    blob = (
        'Billing or credits exhausted: HTTP 402: {"detail":"You\'re out of Plow credits. '
        'Top up ($5 minimum) to keep going: https://app.plow.co/dashboard"}'
    )
    posted = []

    class Transport:
        async def post(self, url, body):
            posted.append(body)

    previous = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        try:
            adapter = line.WhatsAppLine("https://relay.example", Transport())

            async def run():
                await adapter.send("whatsapp:5537999999999", blob)
                await adapter.send("whatsapp:5537999999999", blob)

                async def handler(burst):
                    return burst

                adapter.handle_message = handler
                await adapter.accept({
                    "id": "wamid.IN",
                    "text": "oi",
                    "to": "5537999999999",
                })
                await adapter.send("whatsapp:5537999999999", blob)

            asyncio.run(run())
        finally:
            if previous is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous
    notice = (
        "acabaram os créditos da plow\n"
        "recarrega em app.plow.co/dashboard pra eu continuar"
    )
    assert posted == [
        {"to": "5537999999999", "text": notice},
        {"to": "5537999999999", "text": notice},
    ]


def test_silence_token_is_not_a_whatsapp_bubble():
    import asyncio
    from types import SimpleNamespace

    calls = []

    class Transport:
        async def post(self, url, body):
            calls.append(body)

    adapter = line.WhatsAppLine("https://relay.example/", Transport())
    previous = line._QUIET
    line.bind_outbound(SimpleNamespace(
        is_silence=quiet_is_silence,
        outbound_echo=lambda _text: False,
        turn_copy=lambda _text: False,
        _remember_outbound=lambda _text: None,
    ))

    async def run():
        await adapter.send("whatsapp:5537999999999", "[NO_REPLY]")
        await adapter.send("whatsapp:5537999999999", "oi")

    try:
        asyncio.run(run())
    finally:
        line._QUIET = previous
    assert calls == [{"to": "5537999999999", "text": "oi"}]


def quiet_is_silence(text):
    return " ".join(str(text or "").strip().upper().split()) in {"[NO_REPLY]", "NO_REPLY"}


def test_pairing_code_answers_without_starting_a_turn():
    import asyncio
    import tempfile

    calls = []

    class Transport:
        async def post(self, url, body):
            calls.append((url, body))

    adapter = line.WhatsAppLine("https://relay.example/", Transport())

    async def handler(burst):
        assert burst.text == "oi"
        return False

    adapter.handle_message = handler
    previous = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory() as home:
        os.environ["HERMES_HOME"] = home
        code_path = Path(home) / "zoen" / "whatsapp.code"
        code_path.parent.mkdir()
        code_path.write_text("142857\n", encoding="utf-8")
        try:
            burst = asyncio.run(adapter.accept({
                "id": "wamid.IN",
                "text": "142857",
                "to": "5537999999999",
            }))
            stayed = asyncio.run(adapter.accept({
                "id": "wamid.NEXT",
                "text": "oi",
                "to": "5537999999999",
            }))
        finally:
            if previous is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous
    assert burst is not None and burst.line_id == "whatsapp:5537999999999"
    assert stayed is None
    assert calls == [(
        "https://relay.example/whatsapp/send",
        {"to": "5537999999999", "text": line.HANDSHAKE},
    )]


def test_factory_fails_loud_without_the_hermes_base():
    if line.BasePlatformAdapter is None:
        try:
            line.hermes_adapter(None)
        except RuntimeError as exc:
            assert "BasePlatformAdapter" in str(exc)
        else:
            raise AssertionError("factory returned without Hermes")
    else:
        adapter = line.hermes_adapter(type("Cfg", (), {"extra": {}})())
        assert hasattr(adapter, "connect")
