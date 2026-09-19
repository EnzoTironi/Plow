"""Run inside the built image, with /workspace mounted read-only. No network."""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web

sys.path.insert(0, "/opt/hermes")
sys.path.insert(0, "/opt/plow/zoen")


async def verify(home):
    os.environ["HERMES_HOME"] = home
    os.environ["PLOW_AGENT_TOKEN"] = "local-test-fixture"
    os.environ["PLOW_HOME_CHANNEL"] = "cht_test"
    os.environ["PLOW_API_BASE"] = "http://127.0.0.1:1"
    (Path(home) / "zoen").mkdir()
    (Path(home) / "zoen/VOICE.md").write_text("language: pt\n")
    shutil.copy("/opt/hermes/plow-seed/config.yaml", Path(home) / "config.yaml")
    from hermes_cli.plugins import get_plugin_manager
    manager = get_plugin_manager()
    manager.discover_and_load()
    plow = manager._plugins["plow-chat-platform"].module
    plugin = manager._plugins["zoen-face"].module
    assert plow.INBOUND_DEBOUNCE_SECONDS == plugin.presence.SILENCE
    assert getattr(plow.PlowChatAdapter, "_zoen_presence", False)
    assert "zoen_connections" in manager._plugin_tool_names
    assert manager.invoke_hook("pre_gateway_dispatch", event=SimpleNamespace(internal=True)) == [{"action": "allow"}]
    assert json.loads(plugin.connections.handle({"action": "status", "connector": "google"}))["ok"] is False
    adapter = object.__new__(plow.PlowChatAdapter)
    adapter._active_turn = plow._ACTIVE_TURN
    adapter._seen, adapter._inbound = [], {}
    adapter.auth = {"Authorization": "Bearer local-test-fixture"}
    adapter._typing_last_sent = {}
    adapter.chat_uids = {"cht_test"}
    adapter._chats = {"cht_test": {"uid": "cht_test", "trusted": True,
        "participants": [{"type": "member", "role": "owner", "uid": "usr_test", "provider_key": "test"}]}}
    posted, handed_off = [], []
    release_attachment = asyncio.Event()

    async def resolve(message):
        await release_attachment.wait()
        return [], [], message["body"]

    async def serve(request):
        if request.method == "GET":
            # Real Plow reads took 0.96–2.49s from the local container. A
            # zero-latency fixture hid the former 500ms permission timeout.
            await asyncio.sleep(.8)
            return web.json_response(adapter._chats[request.match_info["chat"]])
        endpoint = request.match_info["endpoint"]
        posted.append((endpoint, await request.json()))
        return web.json_response({"uid": "msg_local_receipt"} if endpoint == "messages" else {})

    async def deliver(burst, resolved, chat):
        event = plow.MessageEvent(text=resolved[-1][2], source=SimpleNamespace(chat_id=chat),
                                  message_id=burst[-1].uid, channel_prompt="policy")
        await adapter._handoff_message(event)

    async def handoff(event):
        handed_off.append(event)

    api = web.Application()

    async def completion(request):
        payload = await request.json()
        assert "msg_last" not in payload["messages"][-1]["content"]
        assert "faz um resumo do documento" in payload["messages"][-1]["content"]
        return web.json_response({"choices": [{"message": {"content": "vou olhar o documento e separar o que importa"}}]})

    api.router.add_post("/v1/chat/completions", completion)
    api.router.add_get("/v1/chats/{chat}", serve)
    api.router.add_post("/v1/chats/{chat}/{endpoint:.*}", serve)
    runner = web.AppRunner(api)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    plow.BASE = f"http://127.0.0.1:{runner.addresses[0][1]}"
    plow._resolve_parts = resolve
    adapter._deliver = deliver
    adapter.handle_message = handoff
    adapter._live_turns = {}
    plow._live = (adapter, asyncio.get_running_loop())
    # A suppressed leftover is a final refusal, never a success or a fallback send.
    suppressed = await adapter._send_with_retry("cht_test", "internal leftover prose")
    assert not suppressed.success and suppressed.suppressed and not posted
    plugin.connections.connection = lambda action, connector: {"ok": True, "connector": connector, "connected": False}
    token = plow._ACTIVE_TURN.set({"owner": True, "dm": True, "authority": True, "chat_uid": "cht_test"})
    try:
        connected = json.loads(await asyncio.to_thread(plugin.connections.handle, {"action": "status", "connector": "google"}))
        assert connected["ok"] is True
    finally:
        plow._ACTIVE_TURN.reset(token)
    token = plow._ACTIVE_TURN.set({"owner": True, "dm": False, "chat_uid": "cht_test"})
    try:
        assert not json.loads(plugin.connections.handle({"action": "connect", "connector": "google"}))["ok"]
    finally:
        plow._ACTIVE_TURN.reset(token)
    message = {"uid": "msg_test", "direction": "inbound", "sender": {"type": "member", "role": "owner", "uid": "usr_test"},
               "body": "faz um resumo do documento", "attachments": [{"url": "deliberately unresolved"}]}
    await adapter._on_message(message, "cht_test")
    await adapter._on_message(message, "cht_test")  # socket/backfill duplicate
    for uid in ("msg_second", "msg_last"):
        await asyncio.sleep(.1)
        await adapter._on_message(dict(message, uid=uid), "cht_test")
    last_received = time.monotonic()
    await asyncio.wait_for(asyncio.gather(*adapter._zoen_reception.tasks), 5)
    elapsed = time.monotonic() - last_received
    assert len([p for p in posted if p[0] == "messages"]) == 1, posted
    assert [p[1]["body"] for p in posted if p[0] == "messages"] == ["vou olhar o documento e separar o que importa"]
    assert [p[0] for p in posted if p[0].endswith("/reactions")] == ["messages/msg_last/reactions"], posted
    assert 1.9 <= elapsed < 5, elapsed
    assert not handed_off, "attachment unexpectedly resolved"
    release_attachment.set()
    await asyncio.wait_for(adapter._inbound["cht_test"][0].join(), 2)
    assert len(handed_off) == 1
    assert handed_off[0].zoen_reception == "sent"
    assert handed_off[0].zoen_dispatch_result["action"] == "allow"
    assert manager.invoke_hook("pre_gateway_dispatch", event=handed_off[0]) == [{"action": "allow"}]
    for _, server in adapter._inbound.values():
        server.cancel()
        await asyncio.gather(server, return_exceptions=True)
    await runner.cleanup()
    print(json.dumps({"plugin_registered": True, "owner_guard": True, "connection_tool_dispatch": True, "ack_before_attachment": True,
                      "socket_replay_deduplicated": True, "handoff_not_lost": True,
                      "ack_after_last_message_ms": round(elapsed * 1000)}))


with tempfile.TemporaryDirectory() as home:
    asyncio.run(verify(home))
