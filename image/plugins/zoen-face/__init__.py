"""First inbound is the Zoen intro. Groups stay quiet unless they are for Zoen."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path("/opt/plow/zoen")
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import face  # noqa: E402


def register(ctx) -> None:
    ctx.register_hook("pre_gateway_dispatch", face.greet_on_dispatch)
