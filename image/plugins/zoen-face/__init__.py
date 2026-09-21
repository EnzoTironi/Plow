"""First inbound is the Zoen intro. Groups stay quiet unless they are for Zoen."""
from __future__ import annotations

import importlib.util
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
from . import owner_profile  # noqa: E402


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


def register(ctx) -> None:
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
    ctx.register_tool(name="zoen_connections", toolset="zoen", schema=connections.SCHEMA,
                      handler=connections.handle, emoji="🔌")
    ctx.register_tool(name="zoen_owner_profile", toolset="zoen", schema=owner_profile.SCHEMA,
                      handler=owner_profile.handle, emoji="👋")
    configure_adapters()
