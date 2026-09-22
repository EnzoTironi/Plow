#!/usr/bin/env python3
"""Transcribe an inbound iMessage audio file on this VM.

    python3 /opt/plow/zoen/listen.py /absolute/path.m4a

Prints the words. Empty stdout and exit 2 means the file could not be heard.
The plow wrap calls `with_transcripts` so the turn text already has the words
when faster-whisper is installed; this CLI is the fallback the model runs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

log = logging.getLogger("zoen-listen")
PLACEHOLDER = "(attachment)"
AUDIO_PREFIX = "audio/"
AUDIO_SUFFIXES = frozenset(
    {".mp3", ".m4a", ".aac", ".wav", ".caf", ".amr", ".ogg", ".opus", ".mpga"}
)
# Multilingual Whisper. The `.en` weights only hear English.
DEFAULT_MODEL = "small"
_models: dict[str, object] = {}


def cache_dir() -> Path:
    raw = (os.environ.get("ZOEN_WHISPER_DIR") or "").strip()
    return Path(raw) if raw else Path("/opt/plow/whisper")


def model_name() -> str:
    """The multilingual weights. An English-only name falls back to the default."""
    raw = (os.environ.get("ZOEN_WHISPER_MODEL") or "").strip() or DEFAULT_MODEL
    if raw.endswith(".en"):
        return DEFAULT_MODEL
    return raw


def is_audio(kind: str | None, path: str | Path | None = None) -> bool:
    mime = (kind or "").split(";", 1)[0].strip().lower()
    if mime.startswith(AUDIO_PREFIX):
        return True
    if mime.startswith("video/"):
        return False
    return Path(path or "").suffix.lower() in AUDIO_SUFFIXES


def _load(name: str):
    if WhisperModel is None:
        return None
    loaded = _models.get(name)
    if loaded is not None:
        return loaded
    kwargs = {"device": "cpu", "compute_type": "int8"}
    root = cache_dir()
    if root.is_dir() or os.environ.get("ZOEN_WHISPER_DIR"):
        kwargs["download_root"] = str(root)
    loaded = WhisperModel(name, **kwargs)
    _models[name] = loaded
    return loaded


def transcribe(path: str | Path, model: str | None = None) -> str:
    source = Path(path)
    if not source.is_file():
        return ""
    try:
        whisper = _load(model or model_name())
    except Exception as exc:
        log.warning("zoen-listen: model unavailable: %s", type(exc).__name__)
        return ""
    if whisper is None:
        return ""
    try:
        segments, _info = whisper.transcribe(
            str(source),
            beam_size=1,
            vad_filter=True,
            language=None,
            task="transcribe",
        )
        parts = [seg.text.strip() for seg in segments if getattr(seg, "text", "").strip()]
    except Exception as exc:
        log.warning("zoen-listen: %s failed: %s", source.name, type(exc).__name__)
        return ""
    return " ".join(parts).strip()


def with_transcripts(
    urls: list,
    kinds: list,
    text: str,
    transcribe_fn=None,
) -> str:
    worker = transcribe if transcribe_fn is None else transcribe_fn
    heard: list[str] = []
    for url, kind in zip(urls, kinds):
        if not is_audio(kind, url):
            continue
        got = worker(url)
        if got:
            heard.append(got)
    if not heard:
        return text
    spoken = "\n".join(heard)
    body = (text or "").strip()
    if not body or body == PLACEHOLDER:
        return spoken
    return f"{body}\n\n{spoken}"


def install(module, transcribe_fn=None) -> bool:
    if getattr(module, "_zoen_listen", False):
        return False
    orig = getattr(module, "_resolve_parts", None)
    if not callable(orig):
        return False
    worker = transcribe_fn

    async def _resolve_parts(msg):
        urls, kinds, text = await orig(msg)
        try:
            merged = await asyncio.wait_for(
                asyncio.to_thread(with_transcripts, urls, kinds, text, worker),
                timeout=45,
            )
        except Exception as exc:
            log.warning("zoen-listen: wrap failed: %s", type(exc).__name__)
            return urls, kinds, text
        return urls, kinds, merged

    module._resolve_parts = _resolve_parts
    module._zoen_listen = True
    return True


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    heard = transcribe(args[0])
    if not heard:
        return 2
    sys.stdout.write(heard + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
