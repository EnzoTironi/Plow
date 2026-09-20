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


async def public_mcp(request):
    message = await request.json()
    if "id" not in message:
        return web.Response(status=202)
    if message["method"] == "initialize":
        result = {"protocolVersion": message["params"]["protocolVersion"], "capabilities": {"tools": {}},
                  "serverInfo": {"name": "public-fixture", "version": "1"}}
    elif message["method"] == "tools/list":
        result = {"tools": [] if request.path == "/empty/mcp" else [
            {"name": "lookup", "description": "Read public fixture data", "inputSchema": {"type": "object", "properties": {}}}]}
    else:
        assert message["method"] == "tools/call" and message["params"]["name"] == "lookup"
        result = {"content": [{"type": "text", "text": "public-fixture-response"}]}
    return web.json_response({"jsonrpc": "2.0", "id": message["id"], "result": result})


async def verify_public_connector(adapter, plow, connections):
    from hermes_cli.mcp_config import _get_mcp_servers
    from tools.mcp_oauth import HermesTokenStorage
    from tools.mcp_tool_lifecycle import shutdown_mcp_servers
    from tools.mcp_tool_schema import mcp_prefixed_tool_name
    from tools.registry import registry

    job = connections.ConnectionJob(adapter, plow, "cht_test", "public-fixture", {"url": plow.BASE + "/mcp"})
    job.task = asyncio.create_task(job.run())
    try:
        await asyncio.wait_for(job.task, 25)
        assert job.status == "tools_ready", job.status
        assert "public-fixture" in _get_mcp_servers()
        assert not HermesTokenStorage("public-fixture").has_cached_tokens()
        result = await asyncio.to_thread(registry.dispatch, mcp_prefixed_tool_name("public-fixture", "lookup"), {})
        assert "public-fixture-response" in str(result), result
        try:
            await asyncio.to_thread(connections.connect_public, "empty-fixture", {"url": plow.BASE + "/empty/mcp"})
            raise AssertionError("empty public connector was saved")
        except RuntimeError as exc:
            assert str(exc) == "public_connector_has_no_tools"
        assert "empty-fixture" not in _get_mcp_servers()
    finally:
        await asyncio.to_thread(shutdown_mcp_servers)


async def verify_catalog(handle):
    catalog = json.loads(await asyncio.to_thread(handle, {"action": "catalog"}))
    assert {"todoist", "notion", "treg", "kiwi", "google", "slack"} <= {entry["name"] for entry in catalog["connectors"]}, catalog
    states = {entry["name"]: entry["availability"] for entry in catalog["connectors"]}
    assert states["kiwi"] == "no_login_required" and states["n8n"] == "requires_operator_setup"
    assert states["unreal-engine"] == "requires_local_application"
    searched = json.loads(await asyncio.to_thread(handle, {"action": "catalog", "query": "treg"}))
    assert [entry["name"] for entry in searched["connectors"]] == ["treg"]
    invalid = json.loads(await asyncio.to_thread(handle, {"action": "connect", "connector": "https://untrusted.example/mcp"}))
    assert invalid["error"] == "connector_not_in_remote_catalog", invalid


async def verify(home):
    os.environ["HERMES_HOME"] = home
    os.environ["PLOW_AGENT_TOKEN"] = "local-test-fixture"
    os.environ["PLOW_HOME_CHANNEL"] = "cht_test"
    os.environ["PLOW_API_BASE"] = "http://127.0.0.1:1"
    (Path(home) / "zoen").mkdir()
    (Path(home) / "zoen/VOICE.md").write_text("language: pt\n")
    shutil.copy("/opt/hermes/plow-seed/config.yaml", Path(home) / "config.yaml")
    from hermes_cli.plugins import get_plugin_manager
    from gateway.config import PlatformConfig
    manager = get_plugin_manager()
    manager.discover_and_load()
    plow = manager._plugins["plow-chat-platform"].module
    plugin = manager._plugins["zoen-face"].module
    assert plow.INBOUND_DEBOUNCE_SECONDS == plugin.presence.SILENCE
    assert getattr(plow.PlowChatAdapter, "_zoen_presence", False)
    assert "zoen_connections" in manager._plugin_tool_names
    assert manager.invoke_hook("pre_gateway_dispatch", event=SimpleNamespace(internal=True)) == [{"action": "allow"}]
    assert json.loads(plugin.connections.handle({"action": "status", "connector": "google"}))["ok"] is False
    adapter = plow.PlowChatAdapter(PlatformConfig())
    plow._wake_mac_link = lambda: None
    adapter._active_turn = plow._ACTIVE_TURN
    adapter._seen, adapter._inbound = [], {}
    adapter.auth = {"Authorization": "Bearer local-test-fixture"}
    adapter._typing_last_sent = {}
    adapter.platform = plow._platform()
    adapter.home_chat_uid = "cht_test"
    adapter._identity = {"lines": []}
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
        event._gateway_accepted = True
        handed_off.append(event)

    api = web.Application()

    async def completion(request):
        payload = await request.json()
        assert "msg_last" not in payload["messages"][-1]["content"]
        assert "faz um resumo do documento" in payload["messages"][-1]["content"]
        return web.json_response({"choices": [{"message": {"content": json.dumps({
            "line": "vou olhar o documento e separar o que importa", "reaction": "like"})}}]})

    api.router.add_post("/v1/chat/completions", completion)
    api.router.add_post("/mcp", public_mcp)
    api.router.add_post("/empty/mcp", public_mcp)
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
    # Exercise actual delivery guards, not just whether the model called a tool.
    from tools.registry import registry
    assert "purpose" in registry.get_schema("plow_send_sequence")["parameters"]["properties"]
    turn = {"owner": True, "dm": True, "authority": True, "chat_uid": "cht_test"}
    token = plow._ACTIVE_TURN.set(turn)
    adapter._live_turns[id(turn)] = turn
    try:
        result = await adapter._send_with_retry("cht_test", "normal final answer", metadata={"notify": True})
        assert result.success and posted[-1][1]["body"] == "normal final answer"
        result = await adapter.send_sequence({"purpose": "progress", "items": [{"type": "text", "body": "contextual opening"}]}, turn)
        assert result["success"] and not turn["reply_delivered"]
        result = await adapter._send_with_retry("cht_test", "result after opening", metadata={"notify": True})
        assert result.success and posted[-1][1]["body"] == "result after opening"
        result = await adapter.send_sequence({"purpose": "answer", "items": [{"type": "text", "body": "final sequence"}]}, turn)
        assert result["success"]
        count = len(posted)
        await adapter._send_with_retry("cht_test", "duplicate trailing answer", metadata={"notify": True})
        assert len(posted) == count
    finally:
        plow._ACTIVE_TURN.reset(token)
        adapter._live_turns.clear()
        posted.clear()
    from integration_owner_profile import verify_owner_profile
    await verify_owner_profile(adapter, plow, plugin)
    plugin.connections.connection = lambda action, connector: {"ok": True, "connector": connector, "connected": False}
    token = plow._ACTIVE_TURN.set({"owner": True, "dm": True, "authority": True, "chat_uid": "cht_test"})
    try:
        connected = json.loads(await asyncio.to_thread(plugin.connections.handle, {"action": "status", "connector": "google"}))
        assert connected["ok"] is True
        assert connected["authentication"] == "zoen_oauth"
        assert "connected" not in connected  # The legacy Plow stub was not called.
        await verify_catalog(plugin.connections.handle)
    finally:
        plow._ACTIVE_TURN.reset(token)
    token = plow._ACTIVE_TURN.set({"owner": True, "dm": False, "chat_uid": "cht_test"})
    try:
        assert not json.loads(plugin.connections.handle({"action": "connect", "connector": "google"}))["ok"]
    finally:
        plow._ACTIVE_TURN.reset(token)
    native_connections = sys.modules[plugin.__name__ + ".mcp_connections"]
    treg = native_connections.server_config("treg")
    assert treg["url"] == "https://treg.to/mcp/v2/" and treg["auth"] == "oauth"
    assert set(treg["tools"]["include"]) == {"catalog_search", "catalog_get", "catalog_call_read", "catalog_call_write", "balance"}
    await native_connections.notify(adapter, plow, "cht_test", "todoist", "Fixture connection result")
    assert len(handed_off) == 1
    assert handed_off[0].internal and handed_off[0].authority
    assert handed_off[0].source.role_authorized and handed_off[0].source.chat_id == "cht_test"
    assert manager.invoke_hook("pre_gateway_dispatch", event=handed_off[0]) == [{"action": "allow"}]
    async def connection_turn(event):
        turn = plow._ACTIVE_TURN.get()
        assert turn and turn["owner"] and turn["dm"] and turn["authority"], turn
        result = json.loads(await asyncio.to_thread(plugin.connections.handle, {"action": "status", "connector": "todoist"}))
        assert result["ok"] and not result["credentials_saved"], result
        return None

    adapter._message_handler = connection_turn
    await adapter._process_message_background(handed_off[0], "connection-fixture")
    assert plow._ACTIVE_TURN.get() is None and not adapter._live_turns
    async def ordinary_model_final(event):
        return "Google account checked; ready for the requested task"
    adapter._message_handler = ordinary_model_final
    await adapter._process_message_background(handed_off[0], "normal-final-fixture")
    assert [body["body"] for endpoint, body in posted if endpoint == "messages"][-1] == "Google account checked; ready for the requested task"
    assert plow._ACTIVE_TURN.get() is None and not adapter._live_turns
    posted.clear()
    handed_off.clear()
    admissions = []
    async def admit_on_retry(event):
        admissions.append(event.message_id)
        event._gateway_accepted = len(admissions) > 1
        if event._gateway_accepted:
            handed_off.append(event)
    adapter.handle_message = admit_on_retry
    await native_connections.notify(adapter, plow, "cht_test", "todoist", "Retry rejected queue admission")
    assert len(admissions) == 2 and len(set(admissions)) == 1 and len(handed_off) == 1
    adapter.handle_message = handoff
    handed_off.clear()
    await verify_public_connector(adapter, plow, native_connections)
    assert len(handed_off) == 1 and "no personal account was connected" in handed_off[0].text
    handed_off.clear()
    adapter._chats["cht_test"]["participants"][0]["role"] = "member"
    try:
        await native_connections.notify(adapter, plow, "cht_test", "todoist", "Must not be delivered")
        raise AssertionError("revoked owner notification was allowed")
    except PermissionError:
        assert not handed_off
    finally:
        adapter._chats["cht_test"]["participants"][0]["role"] = "owner"
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
    assert handed_off[0].zoen_reception == {"status": "sent", "reaction": "sent"}
    assert handed_off[0].zoen_dispatch_result["action"] == "allow"
    assert manager.invoke_hook("pre_gateway_dispatch", event=handed_off[0]) == [{"action": "allow"}]
    for _, server in adapter._inbound.values():
        server.cancel()
        await asyncio.gather(server, return_exceptions=True)
    await runner.cleanup()
    print(json.dumps({"plugin_registered": True, "owner_guard": True, "connection_tool_dispatch": True,
                      "owner_profile_verified": True, "native_contact_naming_preserved": True,
                      "native_final_delivery": True, "progress_preserves_final": True,
                      "answer_sequence_deduplicated": True, "queue_admission_retry": True,
                      "connection_event_native_lifecycle": True, "ack_before_attachment": True,
                      "public_connector_native_read": True, "treg_manifest_valid": True,
                      "socket_replay_deduplicated": True, "handoff_not_lost": True,
                      "ack_after_last_message_ms": round(elapsed * 1000)}))


with tempfile.TemporaryDirectory() as home:
    asyncio.run(verify(home))
