#!/usr/bin/env python3
"""Run: python3 tests/test_zoen_face_quiet.py"""
import asyncio
import importlib.util
import json
import os
import tempfile
import urllib.request
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


def test_sitecustomize_drops_retired_hello_in_any_python():
    spec = importlib.util.spec_from_file_location(
        "zoen_sitecustomize", ROOT / "image/sitecustomize.py"
    )
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    for body in (
        "a gente te ajuda. +55 31 99994-1160",
        "oi, eu sou o Zoen, o monstrinho que faz seus sonhos acontecerem",
        "salva meu cartão pra você saber que sou eu",
    ):
        req = urllib.request.Request(
            "https://example.invalid/v1/chats/cht_x/messages",
            data=json.dumps({"body": body, "format": "none"}).encode(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            assert resp.status == 200
            assert json.loads(resp.read()) == {}


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
        assert result["failure"]["status"] == "delivery_unknown"
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
    assert "You are a Plow assistant" not in soul
    assert "mention /help" in soul.lower()
    assert "zoen_connections" in soul
    assert "zoen_imessage" in soul
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
        "google-workspace",
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
    ):
        assert needle in persona, needle


if __name__ == "__main__":
    test_normal_final_is_dropped()
    test_contract_renames_send_and_forbids_leftover()
    test_leftover_credits_error_becomes_the_dashboard_bubble()
    test_sitecustomize_drops_retired_hello_in_any_python()
    test_retired_hello_http_post_is_dropped()
    test_retired_hello_is_dropped()
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
