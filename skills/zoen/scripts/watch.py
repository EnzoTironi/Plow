#!/usr/bin/env python3
"""Production snapshot: Sentry, PostHog, Cloudflare, Vercel. Missing tokens = skipped.

    watch.py snapshot
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import request  # noqa: E402


def env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def alert(source: str, severity: str, title: str, url: str = "") -> dict:
    return {"source": source, "severity": severity, "title": title, "url": url}


def sentry_snapshot() -> dict:
    token, org = env("SENTRY_AUTH_TOKEN"), env("SENTRY_ORG")
    if not token or not org:
        return {"configured": False, "alerts": [], "error": None}
    result = request(
        "GET",
        f"https://sentry.io/api/0/organizations/{quote(org)}/issues/?query=is:unresolved&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    alerts = []
    body = result["body"] if isinstance(result["body"], list) else []
    for item in body:
        if not isinstance(item, dict):
            continue
        alerts.append(
            alert(
                "sentry",
                str(item.get("level") or "error"),
                str(item.get("title") or "unresolved issue"),
                str(item.get("permalink") or ""),
            )
        )
    return {"configured": True, "alerts": alerts, "error": result["error"]}


def posthog_snapshot() -> dict:
    key = env("POSTHOG_API_KEY")
    host = env("POSTHOG_HOST") or "https://us.i.posthog.com"
    project = env("POSTHOG_PROJECT_ID")
    if not key:
        return {"configured": False, "alerts": [], "error": None}
    url = f"{host.rstrip('/')}/api/projects/"
    if project:
        url = f"{host.rstrip('/')}/api/projects/{quote(project)}/error_tracking/issues/?limit=10"
    result = request("GET", url, headers={"Authorization": f"Bearer {key}"})
    alerts = []
    body = result["body"]
    rows = []
    if isinstance(body, dict):
        rows = body.get("results") or body.get("issues") or []
    if isinstance(body, list):
        rows = body
    if not isinstance(rows, list):
        rows = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = item.get("name") or item.get("title") or item.get("exception_type") or "posthog issue"
        alerts.append(alert("posthog", "error", str(title), str(item.get("url") or "")))
    return {"configured": True, "alerts": alerts[:10], "error": result["error"]}


def cloudflare_snapshot() -> dict:
    token, account = env("CLOUDFLARE_API_TOKEN"), env("CLOUDFLARE_ACCOUNT_ID")
    if not token:
        return {"configured": False, "alerts": [], "error": None}
    headers = {"Authorization": f"Bearer {token}"}
    result = request("GET", "https://api.cloudflare.com/client/v4/user/tokens/verify", headers=headers)
    alerts = []
    if not result["ok"]:
        return {"configured": True, "alerts": [alert("cloudflare", "error", "token verify failed")], "error": result["error"]}
    if account:
        hist = request(
            "GET",
            f"https://api.cloudflare.com/client/v4/accounts/{quote(account)}/alerting/v3/histories?per_page=10",
            headers=headers,
        )
        body = hist["body"] if isinstance(hist["body"], dict) else {}
        rows = body.get("result") if isinstance(body.get("result"), list) else []
        for item in rows:
            if not isinstance(item, dict):
                continue
            alerts.append(
                alert(
                    "cloudflare",
                    str(item.get("alertType") or "info"),
                    str(item.get("name") or item.get("id") or "cloudflare alert"),
                )
            )
    return {"configured": True, "alerts": alerts, "error": result["error"]}


def vercel_snapshot() -> dict:
    token = env("VERCEL_TOKEN")
    if not token:
        return {"configured": False, "alerts": [], "error": None}
    headers = {"Authorization": f"Bearer {token}"}
    team = env("VERCEL_TEAM_ID")
    qs = "?limit=10"
    if team:
        qs += f"&teamId={quote(team)}"
    result = request("GET", f"https://api.vercel.com/v6/deployments{qs}", headers=headers)
    alerts = []
    body = result["body"] if isinstance(result["body"], dict) else {}
    rows = body.get("deployments") if isinstance(body.get("deployments"), list) else []
    for item in rows:
        if not isinstance(item, dict):
            continue
        state = str(item.get("readyState") or "")
        if state in {"ERROR", "ERRORING", "CANCELED"}:
            alerts.append(
                alert(
                    "vercel",
                    "error",
                    f"{item.get('name') or 'deploy'} {state}",
                    f"https://vercel.com/{item.get('id') or ''}",
                )
            )
    return {"configured": True, "alerts": alerts, "error": result["error"]}


def snapshot() -> dict:
    sources = {
        "sentry": sentry_snapshot(),
        "posthog": posthog_snapshot(),
        "cloudflare": cloudflare_snapshot(),
        "vercel": vercel_snapshot(),
    }
    alerts = []
    configured = []
    skipped = []
    for name, payload in sources.items():
        if payload.get("configured"):
            configured.append(name)
            alerts.extend(payload.get("alerts") or [])
        else:
            skipped.append(name)
    return {
        "configured": configured,
        "skipped": skipped,
        "alerts": alerts,
        "sources": sources,
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    action = args[0] if args else "snapshot"
    if action != "snapshot":
        print("watch: only snapshot", file=sys.stderr)
        return 2
    json.dump(snapshot(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
