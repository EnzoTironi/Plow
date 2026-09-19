"""Reception behavior without network, model calls or real conversations."""
import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/zoen/scripts"))
spec = importlib.util.spec_from_file_location("presence", ROOT / "image/plugins/zoen-face/presence.py")
presence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(presence)


class Adapter:
    def __init__(self):
        self._chats = {"cht_owner": {"owner": True}}
        self.typed = []
        self.posts = []

    async def send_typing(self, chat):
        self.typed.append(chat)

    async def _refresh_current_chat(self, chat):
        pass

    def _send_guard(self, chat):
        return None


def message(uid, text="faz uma pesquisa", attachments=None):
    return {"uid": uid, "body": text, "attachments": attachments or [], "sender": {"role": "owner"}}


def receiver(tmp_path, monkeypatch):
    monkeypatch.setattr(presence, "SILENCE", .025)
    monkeypatch.setattr(presence, "MAX_WAIT", .06)
    monkeypatch.setattr(presence, "prior_language", lambda: "pt")
    adapter = Adapter()
    module = SimpleNamespace(_owner_dm=lambda chat: chat.get("owner", False))
    result = presence.Presence(adapter, module, presence.Receipts(tmp_path / "receipts.db"))

    async def post(chat, endpoint, payload):
        adapter.posts.append((chat, endpoint, payload))
        return "sent"

    result.post = post
    return result, adapter


async def drain(receiving):
    while receiving.tasks:
        await asyncio.gather(*receiving.tasks)


def test_burst_one_status_and_reaction_on_last_message(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def run():
        receiving.accept(message("msg_1"), "cht_owner")
        await asyncio.sleep(.005)
        receiving.accept(message("msg_2", "sobre aquele documento"), "cht_owner")
        await drain(receiving)
        event = SimpleNamespace(source=SimpleNamespace(chat_id="cht_owner"), message_id="msg_2", channel_prompt="existing policy")
        await receiving.annotate(event)
        assert "Do not send another status" in event.channel_prompt
        assert event.channel_prompt.startswith("existing policy")

    asyncio.run(run())
    assert adapter.typed == ["cht_owner"]
    assert adapter.posts == [
        ("cht_owner", "messages", {"body": "tô nisso"}),
        ("cht_owner", "messages/msg_2/reactions", {"operation": "add", "type": "like"}),
    ]


def test_attachment_does_not_block_status_with_real_debounce(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    monkeypatch.setattr(presence, "SILENCE", 2.0)
    monkeypatch.setattr(presence, "MAX_WAIT", 3.0)

    async def run():
        started = time.monotonic()
        unresolved = asyncio.Event()
        receiving.accept(message("msg_doc", attachments=[{"url": "pending-download"}]), "cht_owner")
        await drain(receiving)
        assert 1.9 <= time.monotonic() - started < 5
        assert not unresolved.is_set()
        assert adapter.posts[0][1] == "messages"

    asyncio.run(run())


def test_reconnect_does_not_repeat_sent_receipt(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    asyncio.run(send_one(receiving))
    restarted = presence.Presence(adapter, receiving.module, presence.Receipts(tmp_path / "receipts.db"))
    restarted.post = receiving.post
    asyncio.run(send_one(restarted))
    assert len(adapter.posts) == 2


async def send_one(receiving):
    receiving.accept(message("msg_1"), "cht_owner")
    await drain(receiving)


def test_ambiguous_send_is_not_retried_after_restart(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def uncertain(*args):
        adapter.posts.append(args)
        return "uncertain"

    receiving.post = uncertain
    asyncio.run(send_one(receiving))
    asyncio.run(send_one(receiving))
    assert len(adapter.posts) == 2
    assert receiving.receipts.state("cht_owner", "msg_1") == "uncertain"


def test_closer_only_reacts(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def run():
        receiving.accept(message("msg_1", "valeu"), "cht_owner")
        receiving.accept(message("msg_2", "obrigado"), "cht_owner")
        await drain(receiving)

    asyncio.run(run())
    assert adapter.posts == [("cht_owner", "messages/msg_2/reactions", {"operation": "add", "type": "like"})]


def test_revoked_membership_does_not_send(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def revoke(chat):
        adapter._chats[chat] = {"owner": False}

    adapter._refresh_current_chat = revoke
    asyncio.run(send_one(receiving))
    assert adapter.posts == []


def test_sad_content_does_not_receive_a_like():
    assert presence.reaction("preciso de ajuda, meu pai morreu") is None


def test_commands_do_not_receive_an_ack(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def run():
        receiving.accept(message("msg_1", "/stop"), "cht_owner")
        await drain(receiving)

    asyncio.run(run())
    assert adapter.posts == []


def test_continuous_burst_does_not_emit_repeated_statuses(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def run():
        for i in range(10):
            receiving.accept(message(f"msg_{i}"), "cht_owner")
            await asyncio.sleep(.01)
            assert adapter.posts == []
        await drain(receiving)

    asyncio.run(run())
    assert len([p for p in adapter.posts if p[1] == "messages"]) == 1


def test_status_while_previous_work_is_busy(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    adapter._live_turns = {"previous": {"chat_uid": "cht_owner", "reply_delivered": False}}
    asyncio.run(send_one(receiving))
    assert adapter.posts[0][1] == "messages"


def test_slow_language_detection_uses_prior_without_blocking_receipt(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    monkeypatch.setattr(presence, "LANGUAGE_TIMEOUT", .01)

    def slow_language(*args):
        time.sleep(.15)
        return "en"

    monkeypatch.setattr(presence, "detect_language", slow_language)

    async def run():
        started = time.monotonic()
        await send_one(receiving)
        assert time.monotonic() - started < .1

    asyncio.run(run())
    assert adapter.posts[0][2] == {"body": "tô nisso"}
