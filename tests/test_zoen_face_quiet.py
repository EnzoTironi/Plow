#!/usr/bin/env python3
"""Run: python3 tests/test_zoen_face_quiet.py"""
import asyncio
import importlib.util
import tempfile
from pathlib import Path

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
            return "sent"

        async def send_or_update_status(self, chat_id, status_key, content, metadata=None):
            self.posted.append(("status", content))
            return "status"

        async def send_image_file(self, chat_id, image_path, caption=None, **_kwargs):
            self.posted.append(("image", image_path))
            return "image"

        async def send_sequence(self, args, turn, receipt=None):
            self.posted.append(("sequence", args))
            return "sequence"

        async def _send_attachment(self, chat_id, path, *, caption=None, filename=None):
            self.posted.append(("file", path))
            return type("Result", (), {"success": True, "error": None})()

        async def send_typing(self, chat_id, metadata=None):
            self.posted.append(("typing", chat_id))
            return "typing"

    return Adapter


def test_leftover_send_never_posts():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    result = asyncio.run(box.send("cht_x", "Still building. Ending turn."))
    assert box.posted == []
    assert result.success is True
    assert result.error is None


def test_send_sequence_still_runs():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    args = {"items": [{"type": "text", "body": "shipped"}]}
    result = asyncio.run(box.send_sequence(args, {"chat_uid": "cht_x"}))
    assert result == "sequence"
    assert box.posted == [("sequence", args)]


def test_native_file_send_is_dropped_typing_stays():
    Adapter = _adapter()
    quiet.silence(Adapter)
    box = Adapter()
    asyncio.run(box.send_image_file("cht_x", "/tmp/demo.png"))
    asyncio.run(box.send_or_update_status("cht_x", "working", "compiling"))
    asyncio.run(box.send_typing("cht_x"))
    assert box.posted == [("typing", "cht_x")]


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
    assert result.success is True


def test_silence_is_idempotent():
    Adapter = _adapter()
    quiet.silence(Adapter)
    first = Adapter.send
    quiet.silence(Adapter)
    assert Adapter.send is first
    box = Adapter()
    asyncio.run(box.send("cht_x", "Hello leftover"))
    assert box.posted == []


def test_missing_adapter_does_not_raise():
    quiet.log.disabled = True
    try:
        quiet.silence_plow_adapter()
    finally:
        quiet.log.disabled = False


if __name__ == "__main__":
    test_leftover_send_never_posts()
    test_send_sequence_still_runs()
    test_native_file_send_is_dropped_typing_stays()
    test_media_sequence_uploads_file_instead_of_the_path()
    test_media_outside_workspace_is_not_posted_as_text()
    test_silence_is_idempotent()
    test_missing_adapter_does_not_raise()
    print("ok")
