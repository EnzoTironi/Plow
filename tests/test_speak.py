#!/usr/bin/env python3
"""Run: python3 tests/test_speak.py"""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "speak", ROOT / "skills/zoen/scripts/speak.py"
)
speak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(speak)


def test_voice_for_maps_portuguese_and_unknowns():
    assert speak.voice_for("pt") == "pt-br"
    assert speak.voice_for("en") == "en"
    assert speak.voice_for("xx") == "pt-br"
    assert speak.voice_for(None) == "pt-br"


def test_synthesize_writes_m4a_through_espeak_then_ffmpeg(tmp_path, monkeypatch):
    calls = []

    def run(cmd, **_kwargs):
        calls.append(cmd)
        if cmd[0] == "espeak-ng":
            Path(cmd[cmd.index("-w") + 1]).write_bytes(b"RIFF")
        else:
            Path(cmd[-1]).write_bytes(b"ftyp")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(speak.subprocess, "run", run)
    dest = tmp_path / "note.m4a"
    assert speak.synthesize("oi tudo bem", dest, lang="pt") == dest
    assert dest.is_file()
    assert dest.with_suffix(".wav").exists() is False
    assert calls[0][:1] == ["espeak-ng"]
    assert "-w" in calls[0]
    assert calls[0][-1] == "--stdin"
    assert calls[1][0] == "ffmpeg"
    assert calls[1][-1] == str(dest)


def test_synthesize_rejects_empty_text_and_wrong_suffix(tmp_path):
    try:
        speak.synthesize("  ", tmp_path / "note.m4a")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("empty text must fail")
    try:
        speak.synthesize("oi", tmp_path / "note.wav")
    except ValueError as exc:
        assert "m4a" in str(exc)
    else:
        raise AssertionError("wav output must fail")


def test_main_prints_the_output_path(tmp_path, monkeypatch, capsys):
    dest = tmp_path / "zoen.m4a"

    def fake(text, path, lang=None):
        assert text == "oi"
        assert lang == "pt"
        path.write_bytes(b"ftyp")
        return path

    monkeypatch.setattr(speak, "synthesize", fake)
    assert speak.main(["oi", "--out", str(dest)]) == 0
    assert capsys.readouterr().out.strip() == str(dest)


if __name__ == "__main__":
    import tempfile

    test_voice_for_maps_portuguese_and_unknowns()
    with tempfile.TemporaryDirectory() as folder:
        class Box:
            def setattr(self, target, name, value):
                setattr(target, name, value)

        dest = Path(folder) / "note.m4a"
        calls = []

        def run(cmd, **_kwargs):
            calls.append(cmd)
            if cmd[0] == "espeak-ng":
                Path(cmd[cmd.index("-w") + 1]).write_bytes(b"RIFF")
            else:
                Path(cmd[-1]).write_bytes(b"ftyp")
            return subprocess.CompletedProcess(cmd, 0)

        saved = speak.subprocess.run
        speak.subprocess.run = run
        try:
            assert speak.synthesize("oi tudo bem", dest, lang="pt") == dest
        finally:
            speak.subprocess.run = saved
        assert dest.is_file()
    test_synthesize_rejects_empty_text_and_wrong_suffix(Path(tempfile.mkdtemp()))
    print("ok")
