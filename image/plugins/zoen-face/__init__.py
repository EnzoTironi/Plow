"""First inbound is the Zoen intro. Groups stay quiet unless they are for Zoen."""
from __future__ import annotations

import sys
from pathlib import Path

from . import quiet

SCRIPTS = Path("/opt/plow/zoen")
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import face  # noqa: E402


def register(ctx) -> None:
    def on_dispatch(event, **kwargs):
        quiet.silence_plow_adapter()
        return face.greet_on_dispatch(event, **kwargs)

    ctx.register_hook("pre_gateway_dispatch", on_dispatch)
    quiet.silence_plow_adapter()
