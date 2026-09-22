#!/usr/bin/env python3
"""Run: python3 tests/test_listen.py"""
import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "listen", ROOT / "skills/zoen/scripts/listen.py"
)
listen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(listen)


def test_empty_body_becomes_the_transcript():
    assert listen.with_transcripts(
        ["/a.m4a"], ["audio/mp4"], "", transcribe_fn=lambda _path: "oi tudo bem"
    ) == "oi tudo bem"


def test_attachment_placeholder_is_replaced():
    assert listen.with_transcripts(
        ["/a.m4a"], ["audio/mp4"], "(attachment)", transcribe_fn=lambda _path: "oi"
    ) == "oi"


def test_keeps_typed_text_and_appends_the_transcript():
    assert listen.with_transcripts(
        ["/a.m4a"], ["audio/mp4"], "look at this", transcribe_fn=lambda _path: "oi"
    ) == "look at this\n\noi"


def test_ignores_photos():
    assert listen.with_transcripts(
        ["/a.jpg"], ["image/jpeg"], "", transcribe_fn=lambda _path: "nope"
    ) == ""


def test_application_octet_stream_m4a_is_audio():
    assert listen.is_audio("application/octet-stream", "/tmp/note.m4a")
    assert not listen.is_audio("video/mp4", "/tmp/clip.mp4")
    assert listen.is_audio("audio/mp4", "/tmp/note.m4a")


def test_failed_stt_keeps_the_original_text():
    assert listen.with_transcripts(
        ["/a.m4a"], ["audio/mp4"], "", transcribe_fn=lambda _path: ""
    ) == ""


def test_transcription_model_is_multilingual():
    previous = os.environ.get("ZOEN_WHISPER_MODEL")
    try:
        os.environ.pop("ZOEN_WHISPER_MODEL", None)
        assert listen.model_name() == "small"
        assert not listen.model_name().endswith(".en")
        os.environ["ZOEN_WHISPER_MODEL"] = "tiny.en"
        assert listen.model_name() == "small"
        os.environ["ZOEN_WHISPER_MODEL"] = "base"
        assert listen.model_name() == "base"
    finally:
        if previous is None:
            os.environ.pop("ZOEN_WHISPER_MODEL", None)
        else:
            os.environ["ZOEN_WHISPER_MODEL"] = previous


def test_transcribe_missing_file_is_empty():
    assert listen.transcribe("/no/such/zoen-memo.m4a") == ""


def test_install_merges_audio_into_resolve_parts():
    async def orig(_msg):
        return ["/tmp/a.m4a"], ["audio/mp4"], ""

    module = SimpleNamespace(_resolve_parts=orig)
    assert listen.install(module, transcribe_fn=lambda _path: "manda o texto")
    assert listen.install(module) is False
    urls, kinds, text = asyncio.run(module._resolve_parts({}))
    assert urls == ["/tmp/a.m4a"]
    assert kinds == ["audio/mp4"]
    assert text == "manda o texto"


if __name__ == "__main__":
    test_empty_body_becomes_the_transcript()
    test_attachment_placeholder_is_replaced()
    test_keeps_typed_text_and_appends_the_transcript()
    test_ignores_photos()
    test_application_octet_stream_m4a_is_audio()
    test_failed_stt_keeps_the_original_text()
    test_transcription_model_is_multilingual()
    test_transcribe_missing_file_is_empty()
    test_install_merges_audio_into_resolve_parts()
    print("ok")
