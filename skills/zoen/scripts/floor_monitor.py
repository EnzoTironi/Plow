#!/usr/bin/env python3
"""Tell Hermes whether the zoen-floor tick needs the model. Prints one stable line.

zoen-floor runs in Hermes monitor mode: this script runs first on every tick,
and Hermes only wakes the model when the line differs from the last one.

- The owner wrote in the last 72 hours: the line changes every two hours, so
  the floor keeps its two-hour cadence while they are around.
- Quiet for longer: the line only names the day they last wrote, so an idle
  install spends no model turns until they text again.
- Their activity cannot be read: the two-hour line, which is how the floor
  ran before this gate existed.

Always exit 0. Hermes treats a failing monitor as "skip this tick", which
would stop the floor without anyone seeing why.

Owner activity is what Zoen already records: reception.db holds a row per
owner iMessage, and whatsapp.route is rewritten on every WhatsApp turn.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

ACTIVE_SECONDS = 72 * 3600
WINDOW_SECONDS = 2 * 3600


def home() -> Path:
    return Path((os.environ.get("HERMES_HOME") or "/var/lib/hermes").strip() or "/var/lib/hermes")


def last_owner_activity(root: Path) -> float | None:
    """Epoch seconds of the owner's latest message on any line, or None if they never wrote."""
    seen: list[float] = []
    receipts = root / "zoen" / "reception.db"
    if receipts.exists():
        db = sqlite3.connect(f"file:{receipts}?mode=ro", uri=True, timeout=1)
        try:
            row = db.execute("SELECT MAX(updated) FROM receipts").fetchone()
        finally:
            db.close()
        if row and row[0] is not None:
            seen.append(float(row[0]))
    route = root / "zoen" / "whatsapp.route"
    if route.exists():
        seen.append(route.stat().st_mtime)
    return max(seen) if seen else None


def line(root: Path, now: float) -> str:
    window = int(now // WINDOW_SECONDS)
    try:
        last = last_owner_activity(root)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return f"zoen-floor: owner activity unreadable, window {window}"
    if last is None:
        return "zoen-floor: no owner message yet"
    if now - last <= ACTIVE_SECONDS:
        return f"zoen-floor: owner active, window {window}"
    return "zoen-floor: owner quiet since " + time.strftime("%Y-%m-%d", time.gmtime(last))


def main() -> int:
    try:
        print(line(home(), time.time()))
    except Exception:  # never fail the tick: a failed monitor silently skips the floor
        print(f"zoen-floor: monitor error, window {int(time.time() // WINDOW_SECONDS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
