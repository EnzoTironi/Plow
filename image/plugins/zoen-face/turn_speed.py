"""Keep the first reply off probes that do not change it.

Hermes asks the endpoint for the model's context window on every turn, and
that request fails closed for the Plow API. It also re-checks every tool
thirty seconds after the last check. Both finish before the model is asked.
The window is stable, so it is written once. Tool checks stay warm so a
message does not wait on browsers and connectors this process does not have.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("zoen-face")

try:
    from agent.model_metadata import (
        get_cached_context_length,
        get_model_context_length,
        save_context_length,
    )
    from hermes_cli.config import load_config_readonly
except ImportError:  # the host test runner has no Hermes install
    get_cached_context_length = None
    get_model_context_length = None
    load_config_readonly = None
    save_context_length = None

try:
    import tools.registry as tool_registry
except ImportError:
    tool_registry = None

_HOLD_SECONDS = 10
_hold_started = False


def pin_context_window(load=None, cached=None, resolve=None, save=None) -> int:
    """Write the resolved window once. Return that length, or 0 when it was already known."""
    load = load_config_readonly if load is None else load
    cached = get_cached_context_length if cached is None else cached
    resolve = get_model_context_length if resolve is None else resolve
    save = save_context_length if save is None else save
    if load is None or cached is None or resolve is None or save is None:
        return 0
    cfg = load()
    model_cfg = cfg.get("model") if isinstance(cfg, dict) else None
    if not isinstance(model_cfg, dict) or model_cfg.get("context_length"):
        return 0
    model = str(model_cfg.get("default") or "").strip()
    base = str(model_cfg.get("base_url") or "").strip()
    if not model or not base or cached(model, base):
        return 0
    length = resolve(model, base_url=base, provider=str(model_cfg.get("provider") or ""))
    if not isinstance(length, int) or length <= 0:
        return 0
    save(model, base, length)
    log.info("zoen-face pinned the context window at %s tokens", f"{length:,}")
    return length


def touch_tool_checks(cache, lock, now: float) -> int:
    """Move cached tool-check timestamps forward without running the probes again."""
    updated = 0
    with lock:
        for key, entry in list(cache.items()):
            if not isinstance(entry, tuple) or len(entry) != 2 or not isinstance(entry[1], bool):
                continue
            cache[key] = (now, entry[1])
            updated += 1
    return updated


def refresh_tool_checks() -> int:
    registry = tool_registry
    if registry is None:
        return 0
    cache = getattr(registry, "_check_fn_cache", None)
    lock = getattr(registry, "_check_fn_cache_lock", None)
    if cache is None or lock is None:
        return 0
    return touch_tool_checks(cache, lock, time.monotonic())


def _keep_warm() -> None:
    while True:
        time.sleep(_HOLD_SECONDS)
        try:
            refresh_tool_checks()
        except Exception:
            log.debug("zoen-face tool-check refresh failed", exc_info=True)


def install() -> None:
    """Pin the window during startup and keep tool checks off the message path."""
    global _hold_started
    try:
        pin_context_window()
    except Exception:
        log.warning("zoen-face could not pin the context window", exc_info=True)
    if _hold_started:
        return
    _hold_started = True
    threading.Thread(target=_keep_warm, name="zoen-turn-speed", daemon=True).start()
