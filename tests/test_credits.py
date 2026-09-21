#!/usr/bin/env python3
"""Run: python3 tests/test_credits.py"""
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "credits", ROOT / "skills/zoen/scripts/credits.py"
)
credits = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credits)


def test_notice_is_two_lines_without_a_trailing_period():
    for lang, body in credits.NOTICE.items():
        lines = body.splitlines()
        assert len(lines) == 2, lang
        assert not body.endswith(".")
        assert "—" not in body
        assert "app.plow.co/dashboard" in body


def test_looks_like_the_plow_402_blob():
    blob = (
        'HTTP 402: {"detail":"You\'re out of Plow credits. '
        'Top up at app.plow.co/dashboard to keep going."}'
    )
    assert credits.looks_like(blob)
    assert credits.result_is_credits(
        {"ok": False, "status": 402, "body": None, "error": "Payment Required"}
    )
    assert not credits.looks_like("Still building. Ending turn.")
    assert not credits.result_is_credits(
        {"ok": False, "status": 500, "body": None, "error": "nope"}
    )


def test_recently_told_is_scoped_to_home():
    with tempfile.TemporaryDirectory() as d:
        assert not credits.recently_told(d)
        credits.mark_told(credits.notice("en"), d)
        assert credits.recently_told(d)
        assert (Path(d) / "zoen" / "credits").read_text().startswith("plow credits")
        assert not credits.recently_told(d, "whatsapp")
        credits.mark_told(credits.notice("pt"), d, "whatsapp")
        assert credits.recently_told(d, "whatsapp")
        assert (Path(d) / "zoen" / "credits-whatsapp").is_file()


if __name__ == "__main__":
    test_notice_is_two_lines_without_a_trailing_period()
    test_looks_like_the_plow_402_blob()
    test_recently_told_is_scoped_to_home()
    print("ok")
