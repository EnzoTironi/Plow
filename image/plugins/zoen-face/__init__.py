"""First inbound is the Zoen intro. Groups stay quiet unless they are for Zoen."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from . import quiet

_ENABLE = Path("/opt/hermes/enable-zoen-face.py")

SCRIPTS = Path("/opt/plow/zoen")
REPO_SCRIPTS = Path(__file__).resolve().parents[3] / "skills/zoen/scripts"
if SCRIPTS.is_dir():
    sys.modules.pop("face", None)
    if str(SCRIPTS) in sys.path:
        sys.path.remove(str(SCRIPTS))
    sys.path.insert(0, str(SCRIPTS))
elif str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if REPO_SCRIPTS.is_dir() and str(REPO_SCRIPTS) not in sys.path:
    sys.path.append(str(REPO_SCRIPTS))

import face  # noqa: E402
import listen  # noqa: E402
from . import presence  # noqa: E402
from . import connections  # noqa: E402
from . import whatsapp  # noqa: E402
from . import whatsapp_line  # noqa: E402


def _reset_home_skill() -> None:
    if not _ENABLE.is_file():
        return
    spec = importlib.util.spec_from_file_location("enable_zoen_face", _ENABLE)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.refresh_image_scripts()


def configure_adapters():
    for adapter in quiet._adapters():
        quiet.silence(adapter)
        module = sys.modules.get(adapter.__module__)
        if module is None:
            continue
        listen.install(module)
        if hasattr(adapter, "_on_message"):
            quiet.configure_contract(module)
            quiet.claim_identity(module)
            presence.install(adapter, module, face.greet_on_dispatch)


async def _relay_token() -> str:
    """The relay session token. Empty while the bind is still waiting."""
    agent = os.environ.get("PLOW_AGENT_TOKEN", "").strip()
    if not whatsapp._TOKEN:
        await whatsapp._adopt_install(agent)
    if not whatsapp._TOKEN:
        base = os.environ.get("ZOEN_OAUTH_RELAY_URL", "").strip().rstrip("/")
        whatsapp._TOKEN = await whatsapp._register(base) or ""
    return whatsapp._TOKEN or ""


def _whatsapp_factory(cfg):
    return whatsapp_line.hermes_adapter(cfg, authorize=_relay_token)


def register(ctx) -> None:
    whatsapp_line.bind_outbound(quiet)
    whatsapp_line.register_line(ctx, factory=_whatsapp_factory)
    quiet.install_http_filter()
    try:
        _reset_home_skill()
    except Exception:
        pass
    # The pinned Hermes defers platform imports. Materialize Plow before
    # wrapping its adapter, so reception covers the very first inbound burst.
    quiet.watch_registry()
    from gateway.platform_registry import platform_registry
    platform_registry.get("plow-chat")

    def on_dispatch(event, **kwargs):
        configure_adapters()
        prepared = getattr(event, "zoen_dispatch_result", None)
        return prepared if prepared is not None else face.greet_on_dispatch(event, **kwargs)

    ctx.register_hook("pre_gateway_dispatch", on_dispatch)
    ctx.register_hook("pre_tool_call", quiet.guard_whatsapp_tool)
    ctx.register_tool(name="zoen_connections", toolset="zoen", schema=connections.SCHEMA,
                      handler=connections.handle, emoji="🔌")
    configure_adapters()
