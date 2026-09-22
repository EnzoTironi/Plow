"""The first reply does not wait on a context probe or a cold tool check."""
import importlib.util
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "turn_speed", ROOT / "image/plugins/zoen-face/turn_speed.py"
)
speed = importlib.util.module_from_spec(spec)
sys.modules["turn_speed"] = speed
spec.loader.exec_module(speed)


def test_a_known_window_is_written_once():
    saved = {}

    def load():
        return {"model": {"default": "z-ai/glm-5.2", "base_url": "https://api.plow.co/v1", "provider": "plow"}}

    def cached(model, base):
        return saved.get((model, base))

    def resolve(model, base_url, provider):
        assert model == "z-ai/glm-5.2"
        assert base_url == "https://api.plow.co/v1"
        assert provider == "plow"
        return 1_048_576

    def save(model, base, length):
        saved[(model, base)] = length

    assert speed.pin_context_window(load, cached, resolve, save) == 1_048_576
    assert speed.pin_context_window(load, cached, resolve, save) == 0


def test_a_configured_window_is_left_alone():
    def load():
        return {"model": {"default": "z-ai/glm-5.2", "base_url": "https://api.plow.co/v1", "context_length": 128000}}

    def explode(*_args, **_kwargs):
        raise AssertionError("the configured window must not be probed")

    assert speed.pin_context_window(load, explode, explode, explode) == 0


def test_tool_checks_keep_their_answer_and_lose_their_age():
    cache = {("browser", None): (10.0, False), ("files", None): (10.0, True), "skip": "no"}
    updated = speed.touch_tool_checks(cache, threading.Lock(), 40.0)
    assert updated == 2
    assert cache[("browser", None)] == (40.0, False)
    assert cache[("files", None)] == (40.0, True)
    assert cache["skip"] == "no"
