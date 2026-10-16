"""The zoen-floor monitor: wake the model every two hours while the owner is around, never while away."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "zoen" / "scripts" / "floor_monitor.py"
spec = importlib.util.spec_from_file_location("floor_monitor", SCRIPT)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)

HOUR = 3600
NOW = 1_760_000_000.0  # a fixed instant; the line depends only on it and the files


def _owner_wrote(root: Path, at: float) -> None:
    (root / "zoen").mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "zoen" / "reception.db")
    db.execute("CREATE TABLE IF NOT EXISTS receipts (chat TEXT, message TEXT, state TEXT, updated REAL,"
               " status TEXT, reaction TEXT, PRIMARY KEY(chat, message))")
    db.execute("INSERT INTO receipts VALUES ('cht_owner', ?, 'recorded', ?, 'sent', 'sent')", (f"msg_{at}", at))
    db.commit()
    db.close()


def test_active_owner_keeps_the_two_hour_cadence(tmp_path):
    _owner_wrote(tmp_path, NOW - 5 * HOUR)
    first = monitor.line(tmp_path, NOW)
    assert first == monitor.line(tmp_path, NOW + 60)  # same window: Hermes skips the model
    assert first != monitor.line(tmp_path, NOW + 2 * HOUR)  # next window: the model runs
    assert "owner active" in first


def test_quiet_owner_costs_no_model_turns(tmp_path):
    _owner_wrote(tmp_path, NOW - 80 * HOUR)
    lines = {monitor.line(tmp_path, NOW + step * 2 * HOUR) for step in range(36)}
    assert len(lines) == 1  # three days of ticks, one line: the model never wakes
    assert lines.pop().startswith("zoen-floor: owner quiet since ")


def test_a_new_message_wakes_the_floor_again(tmp_path):
    _owner_wrote(tmp_path, NOW - 80 * HOUR)
    before = monitor.line(tmp_path, NOW)
    _owner_wrote(tmp_path, NOW - 60)
    assert monitor.line(tmp_path, NOW) != before


def test_whatsapp_counts_as_owner_activity(tmp_path):
    (tmp_path / "zoen").mkdir()
    route = tmp_path / "zoen" / "whatsapp.route"
    route.write_text("{}")
    os.utime(route, (NOW - HOUR, NOW - HOUR))
    assert "owner active" in monitor.line(tmp_path, NOW)


def test_never_messaged_is_stable(tmp_path):
    assert monitor.line(tmp_path, NOW) == monitor.line(tmp_path, NOW + 50 * HOUR) == "zoen-floor: no owner message yet"


def test_unreadable_state_falls_back_to_the_old_cadence(tmp_path):
    (tmp_path / "zoen").mkdir()
    (tmp_path / "zoen" / "reception.db").write_text("not a database")
    line = monitor.line(tmp_path, NOW)
    assert "unreadable" in line
    assert line != monitor.line(tmp_path, NOW + 2 * HOUR)


def test_the_script_always_exits_zero_with_one_line(tmp_path):
    env = {**os.environ, "HERMES_HOME": str(tmp_path)}
    result = subprocess.run([sys.executable, "-I", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert result.stdout.count("\n") == 1 and result.stdout.startswith("zoen-floor: ")
