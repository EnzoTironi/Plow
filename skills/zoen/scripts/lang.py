"""In-process language id. FastText lid.176 when the model is on disk.

No /v1/chat/completions. Short iMessage lines included. Low confidence
returns the prior VOICE language instead of guessing.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

try:
    import fasttext
except ImportError:
    fasttext = None

FASTTEXT = Path("/opt/plow/lid.176.ftz")
_LABEL = re.compile(r"^__label__([a-z]{2,3})")
_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)
_MODEL = None

# Distinctive function words for Latin-script short SMS. Scripts below
# cover the rest. FastText replaces this when lid.176.ftz loads.
_WORDS: dict[str, frozenset[str]] = {
    "pt": frozenset(
        "que não uma para com você vocês pra isso então também está "
        "são muito bem aqui olá oi tudo faz meu minha sua seu tô "
        "valeu beleza obrigado obrigada pois onde como vamos".split()
    ),
    "en": frozenset(
        "the you that and for are with this have from what your it's "
        "hey hello going don't isn't can't won't please the".split()
    ),
    "es": frozenset(
        "hola qué como cómo una los las para con esto entonces también "
        "está son muy bien aquí hago mi tu sus voy gracias".split()
    ),
    "fr": frozenset(
        "que une pour avec vous cela alors aussi est sont très bien "
        "ici salut fais mon ma ton tes merci je tu nous".split()
    ),
    "de": frozenset(
        "und das die der nicht eine für mit sie ich ist sind hier "
        "bitte danke machen mein deine".split()
    ),
    "it": frozenset(
        "ciao che una per con voi questo allora anche è sono molto "
        "bene qui grazie mio tua".split()
    ),
    "nl": frozenset("het een voor met jij dat dan ook zijn hier alsjeblieft dank".split()),
}

_SCRIPTS: tuple[tuple[str, str], ...] = (
    ("zh", "\u4e00-\u9fff"),
    ("ja", "\u3040-\u30ff"),
    ("ko", "\uac00-\ud7af"),
    ("ar", "\u0600-\u06ff"),
    ("he", "\u0590-\u05ff"),
    ("ru", "\u0400-\u04ff"),
    ("el", "\u0370-\u03ff"),
    ("th", "\u0e00-\u0e7f"),
    ("hi", "\u0900-\u097f"),
    ("bn", "\u0980-\u09ff"),
    ("ta", "\u0b80-\u0bff"),
    ("te", "\u0c00-\u0c7f"),
    ("ml", "\u0d00-\u0d7f"),
    ("gu", "\u0a80-\u0aff"),
    ("pa", "\u0a00-\u0a7f"),
    ("kn", "\u0c80-\u0cff"),
    ("or", "\u0b00-\u0b7f"),
    ("si", "\u0d80-\u0dff"),
    ("my", "\u1000-\u109f"),
    ("km", "\u1780-\u17ff"),
    ("lo", "\u0e80-\u0eff"),
    ("ka", "\u10a0-\u10ff"),
    ("hy", "\u0530-\u058f"),
    ("am", "\u1200-\u137f"),
)


def _lid_path() -> Path:
    env = (os.environ.get("ZOEN_LID") or "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent / "lid.176.ftz"
    if here.is_file():
        return here
    return FASTTEXT


def _fasttext():
    global _MODEL
    if _MODEL is False:
        return None
    if _MODEL is not None:
        return _MODEL
    path = _lid_path()
    if not path.is_file() or fasttext is None:
        _MODEL = False
        return None
    try:
        fasttext.FastText.eprint = lambda *_a, **_k: None
        _MODEL = fasttext.load_model(str(path))
    except Exception:
        _MODEL = False
        return None
    return _MODEL


def _iso(label: str) -> str:
    raw = (label or "").strip().lower()
    match = _LABEL.match(raw)
    if match:
        raw = match.group(1)
    if raw.startswith("zh"):
        return "zh"
    if len(raw) >= 2 and raw[:2].isalpha():
        return raw[:2]
    return ""


def _script(text: str) -> tuple[str, float] | None:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None
    n = len(letters)
    best = ""
    hits = 0
    for iso, block in _SCRIPTS:
        count = sum(1 for ch in letters if re.match(f"[{block}]$", ch))
        if count > hits:
            best, hits = iso, count
    if hits * 2 < n:
        return None
    return best, hits / n


def _words(text: str) -> tuple[str, float] | None:
    tokens = [tok.lower() for tok in _TOKEN.findall(text)]
    if not tokens:
        return None
    scored: list[tuple[str, int]] = []
    for iso, vocab in _WORDS.items():
        scored.append((iso, sum(1 for tok in tokens if tok in vocab)))
    scored.sort(key=lambda item: item[1], reverse=True)
    top, hits = scored[0]
    second = scored[1][1] if len(scored) > 1 else 0
    if hits == 0 or hits == second:
        return None
    return top, hits / max(len(tokens), 1)


def _heuristic(text: str) -> tuple[str, float]:
    script = _script(text)
    if script and script[1] >= 0.6:
        return script
    words = _words(text)
    if words:
        return words
    if script:
        return script
    return "", 0.0


def _predict(text: str) -> tuple[str, float]:
    model = _fasttext()
    line = " ".join((text or "").split())
    if model is not None and line:
        try:
            # fasttext-wheel's predict() builds numpy with copy=False,
            # which raises on NumPy 2. The C binding is the labels.
            raw = model.f.predict(line + "\n", 1, 0.0, "strict")
        except Exception:
            raw = ()
        if raw:
            prob, label = raw[0]
            iso = _iso(str(label))
            if iso:
                return iso, float(prob)
    return _heuristic(text)


def detect_language(text: str, prior: str | None = None) -> str:
    spoken = (text or "").strip()
    fallback = _iso(prior or "") or "en"
    if not spoken:
        return _iso(prior or "") or "pt"
    iso, conf = _predict(spoken)
    letters = sum(1 for ch in spoken if ch.isalpha())
    need = 0.8 if letters < 12 else 0.35
    if not iso or conf < need:
        return fallback if prior else (iso or fallback)
    return iso
