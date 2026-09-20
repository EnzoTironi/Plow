"""Run from integration_image: native Plow contacts plus a loopback profile API."""
import asyncio
import json

from aiohttp import web


async def verify_owner_profile(adapter, plow, plugin):
    from tools.registry import registry
    assert registry.get_schema("zoen_owner_profile")
    profile = {"display_name": None, "photo_url": "https://fixture.invalid/photo.jpg"}
    contacts = [{"provider_key": "test", "display_name": None, "relationship": None, "role": "owner"},
                {"provider_key": "friend@example.test", "display_name": None, "relationship": None, "role": "member"}]
    writes = []

    async def serve_profile(request):
        assert request.headers["Authorization"] == "Bearer local-test-fixture"
        if request.method == "PATCH":
            body = await request.json()
            assert set(body) == {"display_name"}
            writes.append(("profile", body))
            profile.update(body)
            contacts[0]["display_name"] = body["display_name"]
        return web.json_response(profile)

    async def serve_chat(request):
        return web.json_response(adapter._chats["cht_test"])

    async def serve_contacts(request):
        if request.method == "GET":
            return web.json_response(contacts)
        body = await request.json()
        handle = request.match_info["handle"]
        writes.append((handle, body))
        row = next(row for row in contacts if row["provider_key"] == handle)
        row.update(body)
        if row["role"] == "owner":
            profile["display_name"] = body["display_name"]
        return web.json_response(row)

    api = web.Application()
    api.router.add_get("/v1/auth/profile", serve_profile)
    api.router.add_patch("/v1/auth/profile", serve_profile)
    api.router.add_get("/v1/chats/{chat}", serve_chat)
    api.router.add_get("/v1/contacts", serve_contacts)
    api.router.add_put("/v1/contacts/{handle}", serve_contacts)
    runner = web.AppRunner(api)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    previous_base = plow.BASE
    plow.BASE = f"http://127.0.0.1:{runner.addresses[0][1]}"
    turn = {"owner": True, "dm": True, "authority": True, "chat_uid": "cht_test",
            "speaker_handle": "test", "owner_handle": "test", "recall_text": "Ana"}
    token = plow._ACTIVE_TURN.set(turn)
    try:
        await check_onboarding(plugin.owner_profile.handle, writes)
        # The inherited provenance matrix still admits owner and friend names;
        # onboarding must not replace or narrow Plow's existing contact system.
        facts = [{"handle": "test", "display_name": "Nana"},
                 {"handle": "friend@example.test", "display_name": "Jo", "relationship": "friend"}]
        native = plow._admit_people_facts(facts, owner=True, speaker_handle="test", owner_handle="test",
                                         known={row["provider_key"]: row["provider_key"] for row in contacts},
                                         book={row["provider_key"]: row for row in contacts})
        assert native == {"test": {"display_name": "Nana"},
                          "friend@example.test": {"display_name": "Jo", "relationship": "friend"}}, native
        owner_saved = json.loads(await asyncio.to_thread(plow._plow_name_contact,
                                                         {"handle": "test", "display_name": "Nana"}))
        assert owner_saved["success"] and writes[-1] == ("test", {"display_name": "Nana"}), owner_saved
        accepted = json.loads(await asyncio.to_thread(plow._plow_name_contact,
                                                      {"handle": "friend@example.test", "display_name": "Jo", "relationship": "friend"}))
        assert accepted["success"] and accepted["relationship"] == "friend", accepted
        assert writes[-1] == ("friend@example.test", {"display_name": "Jo", "relationship": "friend"})
        assert profile == {"display_name": "Nana", "photo_url": "https://fixture.invalid/photo.jpg"}
    finally:
        plow._ACTIVE_TURN.reset(token)
        plow.BASE = previous_base
        await runner.cleanup()


async def check_onboarding(handle, writes):
    async def call(args):
        return json.loads(await asyncio.to_thread(handle, args))

    assert (await call({"action": "ask"}))["ask"]
    assert not (await call({"action": "ask"}))["ask"]
    public = await call({"action": "save", "name": "Ana"})
    assert public["ok"] and public["verified"] and public["public_name"] == "Ana", public
    assert writes == [("profile", {"display_name": "Ana"})]
    assert not (await call({"action": "ask"}))["ask"]
