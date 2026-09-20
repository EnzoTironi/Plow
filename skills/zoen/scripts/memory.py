#!/usr/bin/env python3
"""Save and search owner memory. Bones only: no voice.

    memory.py remember "Enzo prefers lowercase"
    memory.py remember "fact one" "fact two"
    memory.py recall "enzo cli"
    memory.py correct "old exact fact" "corrected fact"
    memory.py forget "exact fact"
"""
from __future__ import annotations

import json
import fcntl
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from context import zoen_dir  # noqa: E402

FILES = ("VOICE.md", "MEMORY.md", "NOW.md", "JOURNAL.md")
RECALL_LIMIT = 12


def _today() -> str:
    tz = (os.environ.get("TZ") or "America/Sao_Paulo").strip() or "America/Sao_Paulo"
    try:
        zone = ZoneInfo(tz)
    except Exception:
        zone = ZoneInfo("America/Sao_Paulo")
    return datetime.now(zone).date().isoformat()


def _out(payload: dict) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload.get("ok", True) else 1


@contextmanager
def locked_memory(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".memory.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def revise(old: str, new: str | None = None, home: str | None = None) -> dict:
    """Replace/remove exact facts, including copies in the local context files."""
    if not old.strip() or (new is not None and not new.strip()):
        return {"ok": False, "error": "pass the exact old fact and a nonempty replacement"}
    folder = zoen_dir(home)
    changed = 0
    with locked_memory(folder):
        for name in FILES:
            path = folder / name
            if not path.exists():
                continue
            lines = path.read_text().splitlines(keepends=True)
            matches = [i for i, line in enumerate(lines)
                       if re.sub(r"^- \d{4}-\d{2}-\d{2} ", "", line.strip()) == old.strip()]
            if not matches:
                continue
            lines = [line for i, line in enumerate(lines) if i not in matches]
            if new is not None:
                if lines and not lines[-1].endswith("\n"):
                    lines[-1] += "\n"
                prefix = f"- {_today()} " if name in ("MEMORY.md", "JOURNAL.md") else ""
                lines.append(f"{prefix}{new.strip()}\n")
            with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as pending:
                pending.writelines(lines)
            try:
                os.replace(pending.name, path)
            finally:
                Path(pending.name).unlink(missing_ok=True)
            changed += len(matches)
    return {"ok": bool(changed), "changed": changed, "error": None if changed else "exact fact not found; recall first"}


def remember(facts: list[str], home: str | None = None) -> dict:
    lines = [item.strip() for item in facts if item and item.strip()]
    if not lines:
        return {"ok": False, "error": "remember: pass at least one fact"}
    folder = zoen_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "MEMORY.md"
    day = _today()
    block = "".join(f"- {day} {line}\n" for line in lines)
    with locked_memory(folder):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(block)
    return {"ok": True, "wrote": len(lines), "path": str(path)}


def recall(query: str, home: str | None = None, limit: int = RECALL_LIMIT) -> dict:
    needles = [word.lower() for word in query.split() if len(word) > 1]
    if not needles:
        return {"ok": False, "error": "recall: pass a query"}
    folder = zoen_dir(home)
    hits: list[dict] = []
    for name in FILES:
        path = folder / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for index, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            score = sum(1 for needle in needles if needle in low)
            if score:
                hits.append(
                    {"file": name, "line": index, "score": score, "text": line.strip()}
                )
    hits.sort(key=lambda row: (-int(row["score"]), str(row["file"]), -int(row["line"])))
    return {"ok": True, "query": query, "hits": hits[:limit]}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    command = args[0]
    if command == "remember":
        return _out(remember(args[1:]))
    if command == "recall":
        if len(args) < 2:
            return _out({"ok": False, "error": "recall: pass a query"})
        return _out(recall(" ".join(args[1:])))
    if command == "correct" and len(args) == 3:
        return _out(revise(args[1], args[2]))
    if command == "forget" and len(args) == 2:
        return _out(revise(args[1]))
    print("memory: remember | recall | correct | forget", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
