"""Real HTTP boundary, with a local model fixture and no external calls."""
import asyncio
import json
import sys
from pathlib import Path

import pytest
from aiohttp import ClientSession, web

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/zoen/scripts"))
import statusline


@pytest.mark.parametrize("code,content,recent,expected", [
    (200, '{"line":"vou olhar as opções de passeio","reaction":"like"}', [], {"line":"vou olhar as opções de passeio","reaction":"like"}),
    (200, '{"line":null,"reaction":"love"}', [], {"line":None,"reaction":"love"}),
    (429, None, [], None),
    (200, None, [], None),
    (200, 'not JSON', [], None),
    (200, '{"line":"repetida","reaction":"like"}', ["repetida"], {"line":None,"reaction":"like"}),
    (200, '{"line":[],"reaction":"dislike"}', [], {"line":None,"reaction":None}),
])

def test_contextual_opening_or_no_text(tmp_path, code, content, recent, expected):
    async def run():
        async def complete(request):
            payload = await request.json()
            assert payload["model"] == "anthropic/claude-sonnet-5"
            assert payload["thinking"] == {"type": "disabled"}
            assert "Zoen" in payload["messages"][0]["content"]
            context = json.loads(payload["messages"][1]["content"])
            assert context["incoming_burst"][-1]["text"] == "quero um passeio tranquilo"
            assert context["recent_openings_do_not_repeat"] == recent
            return web.json_response({"choices": [{"message": {"content": content}}]}, status=code)

        app = web.Application()
        app.router.add_post("/v1/chat/completions", complete)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        try:
            async with ClientSession(base_url=f"http://127.0.0.1:{runner.addresses[0][1]}") as http:
                result = await statusline.draft([{"body": "quero um passeio tranquilo"}], http=http, home=tmp_path,
                    recent=recent)
            assert result == expected
        finally:
            await runner.cleanup()

    asyncio.run(run())
