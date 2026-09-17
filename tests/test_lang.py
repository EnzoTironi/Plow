#!/usr/bin/env python3
"""Run: python3 tests/test_lang.py"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "lang", ROOT / "skills/zoen/scripts/lang.py"
)
lang = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lang)


def test_detects_portuguese_english_spanish_and_scripts():
    assert lang.detect_language("Oi, tudo bem? faz o CLI pra mim") == "pt"
    assert lang.detect_language("hey, what's going on") == "en"
    assert lang.detect_language("hola, cómo estás") == "es"
    assert lang.detect_language("これは日本語です") == "ja"
    assert lang.detect_language("这是中文") == "zh"
    assert lang.detect_language("هذا عربي") == "ar"


def test_low_confidence_keeps_the_prior_voice_language():
    assert lang.detect_language("ok", prior="pt") == "pt"
    assert lang.detect_language("ok", prior="en") == "en"
    assert lang.detect_language("", prior="es") == "es"
    assert lang.detect_language("") == "pt"


if __name__ == "__main__":
    test_detects_portuguese_english_spanish_and_scripts()
    test_low_confidence_keeps_the_prior_voice_language()
    print("ok")
