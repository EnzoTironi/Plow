"""First inbound is the Zoen intro. Groups stay quiet unless they are for Zoen."""
from __future__ import annotations

import sys
from pathlib import Path

from . import quiet

SCRIPTS = Path("/opt/plow/zoen")
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import face  # noqa: E402
from . import presence  # noqa: E402
from . import connections  # noqa: E402


def configure_adapters():
    for adapter in quiet._adapters():
        quiet.silence(adapter)
        module = sys.modules.get(adapter.__module__)
        if module is not None and hasattr(adapter, "_on_message"):
            quiet.configure_contract(module)
            presence.install(adapter, module, face.greet_on_dispatch)


def register(ctx) -> None:
    # The pinned Hermes defers platform imports. Materialize Plow before
    # wrapping its adapter, so reception covers the very first inbound burst.
    from gateway.platform_registry import platform_registry
    platform_registry.get("plow-chat")

    def on_dispatch(event, **kwargs):
        configure_adapters()
        prepared = getattr(event, "zoen_dispatch_result", None)
        return prepared if prepared is not None else face.greet_on_dispatch(event, **kwargs)

    ctx.register_hook("pre_gateway_dispatch", on_dispatch)
    ctx.register_tool(name="zoen_connections", toolset="zoen", schema=connections.SCHEMA,
                      handler=connections.handle, emoji="🔌")
    configure_adapters()
