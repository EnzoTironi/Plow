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
        self.auth = {}
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
    monkeypatch.setattr(presence, "DRAFT_DELAY", .001)

    async def model_draft(messages, **kwargs):
        return {"line": "vou olhar aquele documento", "reaction": "like"}

    monkeypatch.setattr(presence, "draft", model_draft)
    adapter = Adapter()
    module = SimpleNamespace(BASE="http://fixture", _owner_dm=lambda chat: chat.get("owner", False))
    result = presence.Presence(adapter, module, presence.Receipts(tmp_path / "receipts.db"))

    async def post(chat, endpoint, payload, http, deadline):
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
        assert "do not repeat the opening or reaction" in event.channel_prompt
        assert event.channel_prompt.startswith("existing policy")

    asyncio.run(run())
    assert adapter.typed == ["cht_owner"]
    assert len(adapter.posts) == 2
    assert ("cht_owner", "messages", {"body": "vou olhar aquele documento", "format": "none"}) in adapter.posts
    assert ("cht_owner", "messages/msg_2/reactions", {"operation": "add", "type": "like"}) in adapter.posts


def test_attachment_does_not_block_status_with_real_debounce(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    monkeypatch.setattr(presence, "SILENCE", 2.0)

    async def run():
        started = time.monotonic()
        unresolved = asyncio.Event()
        receiving.accept(message("msg_doc", attachments=[{"url": "pending-download"}]), "cht_owner")
        await drain(receiving)
        assert 1.9 <= time.monotonic() - started < 5
        assert not unresolved.is_set()
        assert any(p[1] == "messages" for p in adapter.posts)

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
    assert receiving.receipts.state("cht_owner", "msg_1") == {"status": "uncertain", "reaction": "uncertain"}


def test_model_selects_reaction_without_status_for_a_closer(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    async def closer(*args, **kwargs):
        return {"line": None, "reaction": "love"}
    monkeypatch.setattr(presence, "draft", closer)

    async def run():
        receiving.accept(message("msg_1", "valeu"), "cht_owner")
        receiving.accept(message("msg_2", "obrigado"), "cht_owner")
        await drain(receiving)

    asyncio.run(run())
    assert adapter.posts == [("cht_owner", "messages/msg_2/reactions", {"operation": "add", "type": "love"})]


def test_revoked_membership_does_not_send(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def revoke(chat):
        adapter._chats[chat] = {"owner": False}

    adapter._refresh_current_chat = revoke
    asyncio.run(send_one(receiving))
    assert adapter.posts == []


def test_permission_read_overlaps_the_burst_window(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    monkeypatch.setattr(presence, "SILENCE", .15)

    async def slow_refresh(chat):
        await asyncio.sleep(.1)

    adapter._refresh_current_chat = slow_refresh

    async def run():
        started = time.monotonic()
        await send_one(receiving)
        assert time.monotonic() - started < .23

    asyncio.run(run())
    assert any(p[1] == "messages" for p in adapter.posts)


def test_new_message_rechecks_membership_before_sending(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    reads = []

    async def refresh(chat):
        reads.append(chat)
        adapter._chats[chat] = {"owner": len(reads) == 1}

    adapter._refresh_current_chat = refresh

    async def run():
        receiving.accept(message("msg_1"), "cht_owner")
        await asyncio.sleep(.005)
        receiving.accept(message("msg_2"), "cht_owner")
        await drain(receiving)

    asyncio.run(run())
    assert len(reads) == 2
    assert adapter.posts == []


def test_permission_timeout_never_uses_the_cached_owner(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    monkeypatch.setattr(presence, "REFRESH_TIMEOUT", .01)

    async def unavailable(chat):
        await asyncio.sleep(.1)

    adapter._refresh_current_chat = unavailable
    asyncio.run(send_one(receiving))
    assert adapter.posts == []
    assert receiving.receipts.state("cht_owner", "msg_1") is None


def test_reaction_is_chosen_by_model_not_keywords(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    async def chosen(*args, **kwargs):
        return {"line": "vou conectar sua agenda", "reaction": "emphasize"}
    monkeypatch.setattr(presence, "draft", chosen)
    async def run():
        receiving.accept(message("msg_connect", "conecta meu Google"), "cht_owner")
        await drain(receiving)
    asyncio.run(run())
    assert adapter.posts[1][2] == {"operation": "add", "type": "emphasize"}


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
    assert any(p[1] == "messages" for p in adapter.posts)


def test_failed_generation_never_sends_a_canned_status(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def unavailable(*args, **kwargs):
        return None

    monkeypatch.setattr(presence, "draft", unavailable)

    async def run():
        await send_one(receiving)
        event = SimpleNamespace(source=SimpleNamespace(chat_id="cht_owner"), message_id="msg_1", channel_prompt="")
        await receiving.annotate(event)
        assert "zoen_imessage" in event.channel_prompt

    asyncio.run(run())
    assert adapter.posts == []
    assert receiving.receipts.state("cht_owner", "msg_1") == {"status": "skipped", "reaction": "skipped"}


def test_new_message_cancels_the_outdated_opening(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def model_draft(messages, **kwargs):
        if len(messages) == 1:
            await asyncio.sleep(.2)
            return {"line": "a stale opening", "reaction": None}
        return {"line": "vou focar no pedido corrigido", "reaction": None}

    monkeypatch.setattr(presence, "draft", model_draft)

    async def run():
        receiving.accept(message("msg_1", "faz uma pesquisa sobre viagens"), "cht_owner")
        await asyncio.sleep(.01)
        receiving.accept(message("msg_2", "na verdade, sobre restaurantes"), "cht_owner")
        await drain(receiving)

    asyncio.run(run())
    assert [p[2]["body"] for p in adapter.posts if p[1] == "messages"] == ["vou focar no pedido corrigido"]


def test_main_work_never_waits_for_slow_reception_and_fast_answer_cancels_opening(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    async def run():
        release = asyncio.Event()
        async def slow_draft(*args, **kwargs):
            await release.wait()
            return {"line": "vou separar as opções", "reaction": "like"}
        monkeypatch.setattr(presence, "draft", slow_draft)
        receiving.accept(message("msg_1"), "cht_owner")
        event = SimpleNamespace(source=SimpleNamespace(chat_id="cht_owner"), message_id="msg_1", channel_prompt="")
        await asyncio.wait_for(receiving.annotate(event), .01)
        assert event.zoen_reception["status"] == "pending"
        receiving.answer_delivered("cht_owner", "msg_1")
        release.set()
        await drain(receiving)
    asyncio.run(run())
    assert adapter.posts == []


def test_new_burst_closes_old_opening_and_keeps_context_in_receive_order(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)

    async def run():
        release_old = asyncio.Event()
        contexts = []

        async def draft(messages, **kwargs):
            contexts.append(kwargs["context"])
            if messages[0]["uid"] == "msg_1":
                await release_old.wait()
            return {"line": messages[0]["body"], "reaction": "like"}

        monkeypatch.setattr(presence, "draft", draft)
        receiving.accept(message("msg_1", "veja a agenda"), "cht_owner")
        await asyncio.sleep(.05)
        assert "cht_owner" not in receiving.bursts  # First draft is still pending.
        receiving.accept(message("msg_2", "comece por amanhã"), "cht_owner")
        release_old.set()
        await drain(receiving)
        assert contexts == [[], ["veja a agenda"]]
        assert receiving.context["cht_owner"] == ["veja a agenda", "comece por amanhã"]

    asyncio.run(run())
    assert [p[2]["body"] for p in adapter.posts if p[1] == "messages"] == ["comece por amanhã"]
    assert all("msg_1" not in p[1] for p in adapter.posts)


def test_each_effect_keeps_its_own_outcome(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    async def mixed(chat, endpoint, *args):
        return "sent" if endpoint == "messages" else "failed"
    receiving.post = mixed
    asyncio.run(send_one(receiving))
    assert receiving.receipts.state("cht_owner", "msg_1") == {"status": "sent", "reaction": "failed"}


def test_expired_budget_never_posts_a_late_opening(tmp_path, monkeypatch):
    receiving, adapter = receiver(tmp_path, monkeypatch)
    monkeypatch.setattr(presence, "DEADLINE", .01)
    asyncio.run(send_one(receiving))
    assert adapter.posts == []
    assert receiving.receipts.state("cht_owner", "msg_1") == {"status": "skipped", "reaction": "skipped"}


def test_legacy_receipts_remain_sealed_against_replay(tmp_path):
    import sqlite3
    path = tmp_path / "receipts.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE receipts (chat TEXT, message TEXT, state TEXT, updated REAL, PRIMARY KEY(chat,message))")
        db.execute("INSERT INTO receipts VALUES ('chat','message','sent',0)")
    receipts = presence.Receipts(path)
    assert receipts.state("chat", "message") == {"status": "uncertain", "reaction": "uncertain"}
    assert not receipts.claim("chat", [{"uid": "message"}])
