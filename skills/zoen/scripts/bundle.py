#!/usr/bin/env python3
"""Pack OCR delegate + DeepSec scan into a delegate_task lot. No LLM here.

    bundle.py --repo /path/to/checkout [--from main --to HEAD] [--commit abc]
              [--max-tasks 10]

Stdlib only. Missing CLIs are listed in `tools`, not fatal: the parent still
gets files from git and can fan out Hermes leaves.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

MAX_TASKS = 10
OCR_TIMEOUT = 120
DEEPSEC_TIMEOUT = 180
GIT_TIMEOUT = 30


class ToolError(RuntimeError):
    pass


def load_json_text(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ToolError("bundle: root JSON must be an object")
    return data


def load_json_file(path: Path) -> dict:
    return load_json_text(path.read_text())


def run_json(argv: list[str], cwd: Path | None, timeout: int) -> dict:
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
        raise ToolError(f"bundle: missing command: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"bundle: timeout: {argv[0]}") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise ToolError(f"bundle: {argv[0]} failed: {err[:500]}")
    try:
        return load_json_text(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError(f"bundle: {argv[0]} did not return JSON") from exc


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise ToolError((proc.stderr or proc.stdout or "git failed").strip()[:500])
    return proc.stdout


def git_paths(repo: Path, from_ref: str | None, to_ref: str | None, commit: str | None) -> list[dict]:
    if commit:
        raw = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit)
    elif from_ref and to_ref:
        raw = git(repo, "diff", "--name-only", f"{from_ref}...{to_ref}")
    else:
        raw = git(repo, "diff", "--name-only", "HEAD")
        extra = git(repo, "ls-files", "--others", "--exclude-standard")
        raw = raw + extra
    files = []
    seen: set[str] = set()
    for line in raw.splitlines():
        path = line.strip()
        if not path or path in seen:
            continue
        seen.add(path)
        files.append({"path": path, "status": "modified", "insertions": 0, "deletions": 0})
    return files


def preview_files(preview: dict) -> list[dict]:
    out = []
    for item in preview.get("reviewable_files") or []:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        out.append(
            {
                "path": item["path"],
                "status": item.get("status") or "modified",
                "insertions": int(item.get("insertions") or 0),
                "deletions": int(item.get("deletions") or 0),
            }
        )
    return out


def rule_groups(rules: dict) -> list[dict]:
    out = []
    for group in rules.get("groups") or []:
        if not isinstance(group, dict):
            continue
        files = [p for p in (group.get("files") or []) if p]
        if not files:
            continue
        out.append(
            {
                "group_id": group.get("group_id"),
                "source": group.get("source") or "",
                "pattern": group.get("pattern") or "",
                "files": files,
                "rule": group.get("rule") or "",
            }
        )
    return out


def harvest_deepsec(data_dir: Path) -> list[dict]:
    """Read DeepSec FileRecords. Only regex candidates, never AI findings."""
    out: list[dict] = []
    if not data_dir.is_dir():
        return out
    skip = {"project.json", "config.json"}
    for path in data_dir.rglob("*.json"):
        if path.name in skip:
            continue
        try:
            rec = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rec, dict):
            continue
        file_path = rec.get("filePath") or rec.get("file_path")
        if not file_path:
            continue
        for cand in rec.get("candidates") or []:
            if not isinstance(cand, dict):
                continue
            lines = cand.get("lineNumbers") or cand.get("line_numbers") or []
            out.append(
                {
                    "path": file_path,
                    "vuln_slug": cand.get("vulnSlug") or cand.get("vuln_slug") or "",
                    "lines": list(lines),
                    "snippet": cand.get("snippet") or "",
                    "pattern": cand.get("matchedPattern") or cand.get("matched_pattern") or "",
                }
            )
    return out


def render_prompt(task: dict) -> str:
    files = ", ".join(task["files"])
    kind = task["kind"] if task["kind"] == "deepsec-cluster" else "ocr-bundle"
    lines = [
        "Review only these files. Do not open a PR. Do not comment on GitHub. Do not fire Latch.",
        "Return JSON: file, line, severity, verdict, evidence, rule.",
        "verdict: act | consider | noted | dismissed. No evidence in the file = dismissed.",
        f"kind: {kind}",
        f"files: {files}",
    ]
    if task.get("rule"):
        lines.append("OCR rule:\n" + str(task["rule"])[:4000])
    if task.get("candidates"):
        lines.append("DeepSec regex candidates (not findings):")
        for cand in task["candidates"][:20]:
            slug = cand.get("vuln_slug") or "?"
            ln = ",".join(str(n) for n in (cand.get("lines") or [])[:8])
            snippet = (cand.get("snippet") or "").replace("\n", " ")[:160]
            lines.append(f"- {cand.get('path')}:{ln} {slug} {snippet}")
    return "\n".join(lines)


def pack(
    files: list[dict],
    groups: list[dict],
    candidates: list[dict],
    max_tasks: int = MAX_TASKS,
) -> tuple[list[dict], list[str]]:
    """One task per OCR rule group, then leftover files, then DeepSec-only paths.

    Overflow is a file list for a second delegate_task lot, not a merged blob.
    """
    if max_tasks < 1:
        raise ToolError("bundle: --max-tasks must be >= 1")
    by_file: dict[str, list[dict]] = {}
    for cand in candidates:
        by_file.setdefault(cand["path"], []).append(cand)

    tasks: list[dict] = []
    used: set[str] = set()
    for group in groups:
        paths = group["files"]
        used.update(paths)
        cands = [c for p in paths for c in by_file.get(p, [])]
        tasks.append(
            {
                "kind": "ocr-bundle",
                "files": paths,
                "rule": group.get("rule") or None,
                "candidates": cands,
            }
        )
    for item in files:
        path = item["path"]
        if path in used:
            continue
        used.add(path)
        tasks.append(
            {
                "kind": "ocr-bundle",
                "files": [path],
                "rule": None,
                "candidates": list(by_file.get(path, [])),
            }
        )
    for path in sorted(by_file):
        if path in used:
            continue
        used.add(path)
        tasks.append(
            {
                "kind": "deepsec-cluster",
                "files": [path],
                "rule": None,
                "candidates": list(by_file[path]),
            }
        )

    def weight(task: dict) -> tuple[int, int]:
        return (len(task["candidates"]), len(task["files"]))

    tasks.sort(key=weight, reverse=True)
    overflow_files: list[str] = []
    for extra in tasks[max_tasks:]:
        overflow_files.extend(extra["files"])
    tasks = tasks[:max_tasks]
    for index, task in enumerate(tasks, 1):
        task["id"] = f"t{index}"
        task["prompt"] = render_prompt(task)
    return tasks, list(dict.fromkeys(overflow_files))


def ocr_preview(repo: Path, from_ref: str | None, to_ref: str | None, commit: str | None) -> dict:
    argv = ["ocr", "delegate", "preview", "--format", "json", "--repo", str(repo)]
    if commit:
        argv.extend(["--commit", commit])
    elif from_ref and to_ref:
        argv.extend(["--from", from_ref, "--to", to_ref])
    return run_json(argv, cwd=repo, timeout=OCR_TIMEOUT)


def ocr_rules(repo: Path, paths: list[str]) -> dict:
    if not paths:
        return {"schema_version": "1", "groups": []}
    argv = ["ocr", "delegate", "rule", "--format", "json", "--repo", str(repo), *paths]
    return run_json(argv, cwd=repo, timeout=OCR_TIMEOUT)


def deepsec_data_dirs(repo: Path) -> list[Path]:
    found = []
    for candidate in (repo / ".deepsec" / "data", repo / "data"):
        if candidate.is_dir():
            found.append(candidate)
    return found


def run_json_or_ok(argv: list[str], cwd: Path, timeout: int) -> None:
    """init --scaffold-only is not JSON; success is exit 0."""
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
        raise ToolError(f"bundle: missing command: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"bundle: timeout: {argv[0]}") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise ToolError(f"bundle: {argv[0]} failed: {err}")


def run_deepsec_scan(repo: Path) -> None:
    binary = shutil.which("deepsec")
    if binary is None:
        raise ToolError("bundle: deepsec not on PATH")
    ws = repo / ".deepsec"
    if not ws.exists():
        run_json_or_ok([binary, "init", "--scaffold-only"], cwd=repo, timeout=DEEPSEC_TIMEOUT)
    argv = [binary, "scan", "--root", str(repo)]
    cwd = ws if ws.is_dir() else repo
    proc = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=DEEPSEC_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise ToolError(f"bundle: deepsec scan failed: {err}")


def bundle(
    repo: Path,
    from_ref: str | None = None,
    to_ref: str | None = None,
    commit: str | None = None,
    max_tasks: int = MAX_TASKS,
    preview: dict | None = None,
    rules: dict | None = None,
    deepsec_data: Path | None = None,
    skip_ocr: bool = False,
    skip_deepsec: bool = False,
) -> dict:
    tools = {"ocr": False, "deepsec": False, "git": shutil.which("git") is not None}
    errors: list[str] = []
    files: list[dict] = []
    groups: list[dict] = []
    candidates: list[dict] = []
    mode = "workspace"
    merge_base = ""

    if preview is None and not skip_ocr and shutil.which("ocr"):
        try:
            preview = ocr_preview(repo, from_ref, to_ref, commit)
            tools["ocr"] = True
        except ToolError as exc:
            errors.append(str(exc))
    elif preview is not None:
        tools["ocr"] = True

    if preview:
        files = preview_files(preview)
        mode = str(preview.get("mode") or mode)
        merge_base = str(preview.get("merge_base") or "")
        from_ref = from_ref or preview.get("from")
        to_ref = to_ref or preview.get("to")
        commit = commit or preview.get("commit")

    if not files and tools["git"]:
        try:
            files = git_paths(repo, from_ref, to_ref, commit)
        except ToolError as exc:
            errors.append(str(exc))

    if rules is None and tools["ocr"] and files and not skip_ocr:
        try:
            rules = ocr_rules(repo, [item["path"] for item in files])
        except ToolError as exc:
            errors.append(str(exc))
            rules = {"groups": []}
    if rules:
        groups = rule_groups(rules)

    if deepsec_data is not None:
        candidates = harvest_deepsec(deepsec_data)
        tools["deepsec"] = True
    elif not skip_deepsec:
        try:
            run_deepsec_scan(repo)
            tools["deepsec"] = True
        except ToolError as exc:
            errors.append(str(exc))
        for data_dir in deepsec_data_dirs(repo):
            harvested = harvest_deepsec(data_dir)
            if harvested:
                candidates = harvested
                tools["deepsec"] = True
                break

    tasks, overflow_files = pack(files, groups, candidates, max_tasks=max_tasks)
    return {
        "repo": str(repo),
        "mode": mode,
        "from": from_ref,
        "to": to_ref,
        "commit": commit,
        "merge_base": merge_base,
        "tools": tools,
        "errors": errors,
        "files": files,
        "rule_groups": groups,
        "candidates": candidates,
        "tasks": tasks,
        "overflow_files": overflow_files,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--from")
    parser.add_argument("--to")
    parser.add_argument("--commit")
    parser.add_argument("--max-tasks", type=int, default=MAX_TASKS)
    parser.add_argument("--preview-json", type=Path)
    parser.add_argument("--rules-json", type=Path)
    parser.add_argument("--deepsec-data", type=Path)
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--skip-deepsec", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    repo = Path(args.repo).resolve()
    preview = load_json_file(args.preview_json) if args.preview_json else None
    rules = load_json_file(args.rules_json) if args.rules_json else None
    from_ref = getattr(args, "from")
    payload = bundle(
        repo,
        from_ref=from_ref,
        to_ref=args.to,
        commit=args.commit,
        max_tasks=args.max_tasks,
        preview=preview,
        rules=rules,
        deepsec_data=args.deepsec_data,
        skip_ocr=args.skip_ocr or preview is not None,
        skip_deepsec=args.skip_deepsec or args.deepsec_data is not None,
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ToolError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
