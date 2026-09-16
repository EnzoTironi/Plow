#!/usr/bin/env python3
"""PR Lens: validate / render / canvas push. SMS gets the view URL only, never #w=.

    lens.py push --repo /path/to/checkout [--graph .pr-lens/drawn.graph.json]

Hermes writes graph.json (agent-skill). Never `pr-lens analyze` with a vendor key.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VIEW_RE = re.compile(r"https://[^\s]+/c/[A-Za-z0-9_-]{22}")


class LensError(RuntimeError):
    pass


def parse_view_url(text: str) -> str | None:
    match = VIEW_RE.search(text or "")
    return match.group(0) if match else None


def run(argv: list[str], cwd: Path, timeout: int = 120) -> str:
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise LensError(f"lens: missing {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LensError(f"lens: timeout {argv[0]}") from exc
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise LensError(out.strip()[:800] or f"lens: {argv[0]} exit {proc.returncode}")
    return out


def binary() -> str:
    return shutil.which("pr-lens") or shutil.which("pr-lens-cli") or "pr-lens"


def push(repo: Path, graph: Path | None = None) -> dict:
    cwd = repo
    graph = graph or (repo / ".pr-lens" / "drawn.graph.json")
    raw = repo / ".pr-lens" / "graph.json"
    bin_name = binary()
    steps = []
    if raw.exists():
        steps.append(["validate", str(raw)])
        run([bin_name, "validate", str(raw)], cwd=cwd)
        run([bin_name, "render", str(raw)], cwd=cwd)
    elif graph.exists():
        steps.append(["validate", str(graph)])
        run([bin_name, "validate", str(graph)], cwd=cwd)
    else:
        return {
            "ok": False,
            "error": "no .pr-lens/graph.json. parent must write the document first",
            "view_url": None,
        }
    text = run([bin_name, "canvas", "push"], cwd=cwd)
    view = parse_view_url(text)
    return {"ok": bool(view), "view_url": view, "raw": text[-500:], "error": None if view else "no view URL"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["push", "parse"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--graph")
    parser.add_argument("--text", help="parse a view URL out of text (tests)")
    args = parser.parse_args(argv)
    if args.action == "parse":
        json.dump({"view_url": parse_view_url(args.text or "")}, sys.stdout)
        sys.stdout.write("\n")
        return 0
    try:
        payload = push(Path(args.repo).resolve(), Path(args.graph) if args.graph else None)
    except LensError as exc:
        payload = {"ok": False, "view_url": None, "error": str(exc)}
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
