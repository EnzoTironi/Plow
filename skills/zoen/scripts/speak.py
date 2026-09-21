#!/usr/bin/env python3
"""Write a local voice memo for zoen_imessage VOICE:.

    python3 /opt/plow/zoen/speak.py "the words" --out /tmp/zoen.m4a
    python3 /opt/plow/zoen/speak.py "hello" --lang en --out /tmp/zoen.m4a

espeak-ng writes wav; ffmpeg (already on the image) makes m4a or mp3.
Prints the output path. No connector. No cloud TTS.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

VOICES = {
    "pt": "pt-br",
    "en": "en",
    "es": "es",
    "fr": "fr",
    "de": "de",
    "it": "it",
}
DEFAULT_OUT = Path("/tmp/zoen.m4a")
AUDIO_SUFFIXES = {".m4a", ".mp3"}


def voice_for(lang: str | None) -> str:
    key = (lang or "pt").strip().lower()[:2]
    return VOICES.get(key, "pt-br")


def _encode(wav: Path, dest: Path) -> list[str]:
    suffix = dest.suffix.lower()
    if suffix == ".m4a":
        return [
            "ffmpeg", "-y", "-i", str(wav),
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
            str(dest),
        ]
    if suffix == ".mp3":
        return [
            "ffmpeg", "-y", "-i", str(wav),
            "-c:a", "libmp3lame", "-q:a", "5",
            str(dest),
        ]
    raise ValueError("speak: --out must be .m4a or .mp3")


def synthesize(text: str, dest: Path, lang: str | None = None) -> Path:
    words = text.strip()
    if not words:
        raise ValueError("speak: empty text")
    dest = dest.expanduser()
    if dest.suffix.lower() not in AUDIO_SUFFIXES:
        raise ValueError("speak: --out must be .m4a or .mp3")
    dest.parent.mkdir(parents=True, exist_ok=True)
    wav = dest.with_name(dest.stem + ".wav")
    try:
        subprocess.run(
            ["espeak-ng", "-v", voice_for(lang), "-s", "165", "-w", str(wav), "--stdin"],
            input=words,
            text=True,
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            _encode(wav, dest),
            check=True,
            capture_output=True,
            timeout=30,
        )
    finally:
        wav.unlink(missing_ok=True)
    if not dest.is_file():
        raise RuntimeError("speak: encoder produced no file")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--lang", default="pt")
    args = parser.parse_args(argv)
    try:
        path = synthesize(args.text, Path(args.out), lang=args.lang)
    except (ValueError, RuntimeError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"speak: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(str(path) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
