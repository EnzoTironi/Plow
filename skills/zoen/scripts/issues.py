#!/usr/bin/env python3
"""GitHub + Linear issues.

    issues.py github list|get|create|update|comment ...
    issues.py linear list|get|create|update|comment ...

Auth: GH_TOKEN or GITHUB_TOKEN; LINEAR_API_KEY. Optional GITHUB_REPO, LINEAR_TEAM_ID.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import request  # noqa: E402

GITHUB = "https://api.github.com"
LINEAR = "https://api.linear.app/graphql"


def _out(payload: dict) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload.get("ok", True) else 1


def github_token() -> str:
    return (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()


def github_headers() -> dict[str, str]:
    token = github_token()
    if not token:
        raise SystemExit("issues: set GH_TOKEN or GITHUB_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "zoen",
    }


def split_repo(repo: str | None) -> tuple[str, str]:
    value = (repo or os.environ.get("GITHUB_REPO") or "").strip()
    if "/" not in value:
        raise SystemExit("issues: pass --repo owner/name or set GITHUB_REPO")
    owner, name = value.split("/", 1)
    if not owner or not name or "/" in name:
        raise SystemExit("issues: --repo must be owner/name")
    return owner, name


def github_list(repo: str | None, state: str = "open") -> dict:
    owner, name = split_repo(repo)
    result = request(
        "GET",
        f"{GITHUB}/repos/{quote(owner)}/{quote(name)}/issues?state={quote(state)}&per_page=20",
        headers=github_headers(),
    )
    issues = []
    if result["ok"] and isinstance(result["body"], list):
        for item in result["body"]:
            if not isinstance(item, dict) or item.get("pull_request"):
                continue
            issues.append(
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "url": item.get("html_url"),
                }
            )
    return {"ok": result["ok"], "error": result["error"], "issues": issues}


def github_get(repo: str | None, number: int) -> dict:
    owner, name = split_repo(repo)
    result = request(
        "GET",
        f"{GITHUB}/repos/{quote(owner)}/{quote(name)}/issues/{number}",
        headers=github_headers(),
    )
    item = result["body"] if isinstance(result["body"], dict) else {}
    return {
        "ok": result["ok"],
        "error": result["error"],
        "issue": None
        if not result["ok"]
        else {
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "body": item.get("body") or "",
            "url": item.get("html_url"),
        },
    }


def github_create(repo: str | None, title: str, body: str) -> dict:
    owner, name = split_repo(repo)
    result = request(
        "POST",
        f"{GITHUB}/repos/{quote(owner)}/{quote(name)}/issues",
        headers=github_headers(),
        body={"title": title, "body": body or ""},
    )
    item = result["body"] if isinstance(result["body"], dict) else {}
    return {
        "ok": result["ok"],
        "error": result["error"],
        "url": item.get("html_url"),
        "number": item.get("number"),
    }


def github_update(
    repo: str | None,
    number: int,
    title: str | None,
    body: str | None,
    state: str | None,
) -> dict:
    owner, name = split_repo(repo)
    payload: dict = {}
    if title:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state:
        payload["state"] = state
    result = request(
        "PATCH",
        f"{GITHUB}/repos/{quote(owner)}/{quote(name)}/issues/{number}",
        headers=github_headers(),
        body=payload,
    )
    item = result["body"] if isinstance(result["body"], dict) else {}
    return {"ok": result["ok"], "error": result["error"], "url": item.get("html_url")}


def github_comment(repo: str | None, number: int, body: str) -> dict:
    owner, name = split_repo(repo)
    result = request(
        "POST",
        f"{GITHUB}/repos/{quote(owner)}/{quote(name)}/issues/{number}/comments",
        headers=github_headers(),
        body={"body": body},
    )
    item = result["body"] if isinstance(result["body"], dict) else {}
    return {"ok": result["ok"], "error": result["error"], "url": item.get("html_url")}


def linear_key() -> str:
    key = (os.environ.get("LINEAR_API_KEY") or "").strip()
    if not key:
        raise SystemExit("issues: set LINEAR_API_KEY")
    return key


def linear_graphql(query: str, variables: dict | None = None) -> dict:
    return request(
        "POST",
        LINEAR,
        headers={"Authorization": linear_key(), "Content-Type": "application/json"},
        body={"query": query, "variables": variables or {}},
    )


def _linear_issue_uuid(identifier: str) -> str | None:
    result = linear_graphql(
        "query ($id: String!) { issue(id: $id) { id } }",
        {"id": identifier},
    )
    body = result["body"] if isinstance(result["body"], dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    issue = data.get("issue") if isinstance(data.get("issue"), dict) else {}
    uuid = issue.get("id")
    return str(uuid) if uuid else None


def linear_list() -> dict:
    result = linear_graphql(
        """
        query {
          issues(filter: { state: { type: { nin: ["completed", "canceled"] } } }, first: 20) {
            nodes { identifier title url state { name } }
          }
        }
        """
    )
    nodes = []
    body = result["body"] if isinstance(result["body"], dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    issues = data.get("issues") if isinstance(data.get("issues"), dict) else {}
    for node in issues.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        state = node.get("state") if isinstance(node.get("state"), dict) else {}
        nodes.append(
            {
                "id": node.get("identifier"),
                "title": node.get("title"),
                "url": node.get("url"),
                "state": state.get("name"),
            }
        )
    err = result["error"]
    if isinstance(body.get("errors"), list) and body["errors"]:
        err = str(body["errors"][0])
    return {"ok": result["ok"] and not body.get("errors"), "error": err, "issues": nodes}


def linear_get(identifier: str) -> dict:
    result = linear_graphql(
        """
        query ($id: String!) {
          issue(id: $id) { identifier title url description state { name } }
        }
        """,
        {"id": identifier},
    )
    body = result["body"] if isinstance(result["body"], dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    issue = data.get("issue") if isinstance(data.get("issue"), dict) else None
    return {"ok": bool(issue), "error": result["error"], "issue": issue}


def linear_create(title: str, body: str, team_id: str | None) -> dict:
    team = (team_id or os.environ.get("LINEAR_TEAM_ID") or "").strip()
    if not team:
        raise SystemExit("issues: pass --team or set LINEAR_TEAM_ID")
    result = linear_graphql(
        """
        mutation ($input: IssueCreateInput!) {
          issueCreate(input: $input) { success issue { identifier url } }
        }
        """,
        {"input": {"title": title, "description": body or "", "teamId": team}},
    )
    body_json = result["body"] if isinstance(result["body"], dict) else {}
    data = body_json.get("data") if isinstance(body_json.get("data"), dict) else {}
    created = data.get("issueCreate") if isinstance(data.get("issueCreate"), dict) else {}
    issue = created.get("issue") if isinstance(created.get("issue"), dict) else {}
    return {
        "ok": bool(created.get("success")),
        "error": result["error"],
        "id": issue.get("identifier"),
        "url": issue.get("url"),
    }


def linear_update(identifier: str, title: str | None, body: str | None) -> dict:
    uuid = _linear_issue_uuid(identifier)
    if not uuid:
        return {"ok": False, "error": "issue not found"}
    incoming: dict = {}
    if title:
        incoming["title"] = title
    if body is not None:
        incoming["description"] = body
    result = linear_graphql(
        """
        mutation ($id: String!, $input: IssueUpdateInput!) {
          issueUpdate(id: $id, input: $input) { success issue { identifier url } }
        }
        """,
        {"id": uuid, "input": incoming},
    )
    body_json = result["body"] if isinstance(result["body"], dict) else {}
    data = body_json.get("data") if isinstance(body_json.get("data"), dict) else {}
    updated = data.get("issueUpdate") if isinstance(data.get("issueUpdate"), dict) else {}
    issue_out = updated.get("issue") if isinstance(updated.get("issue"), dict) else {}
    return {
        "ok": bool(updated.get("success")),
        "error": result["error"],
        "url": issue_out.get("url"),
    }


def linear_comment(identifier: str, body: str) -> dict:
    uuid = _linear_issue_uuid(identifier)
    if not uuid:
        return {"ok": False, "error": "issue not found"}
    result = linear_graphql(
        """
        mutation ($input: CommentCreateInput!) {
          commentCreate(input: $input) { success comment { url } }
        }
        """,
        {"input": {"issueId": uuid, "body": body}},
    )
    body_json = result["body"] if isinstance(result["body"], dict) else {}
    data = body_json.get("data") if isinstance(body_json.get("data"), dict) else {}
    created = data.get("commentCreate") if isinstance(data.get("commentCreate"), dict) else {}
    comment = created.get("comment") if isinstance(created.get("comment"), dict) else {}
    return {"ok": bool(created.get("success")), "error": result["error"], "url": comment.get("url")}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="tracker", required=True)
    gh = sub.add_parser("github")
    gh_sub = gh.add_subparsers(dest="action", required=True)
    p = gh_sub.add_parser("list")
    p.add_argument("--repo")
    p.add_argument("--state", default="open")
    p = gh_sub.add_parser("get")
    p.add_argument("--repo")
    p.add_argument("--number", type=int, required=True)
    p = gh_sub.add_parser("create")
    p.add_argument("--repo")
    p.add_argument("--title", required=True)
    p.add_argument("--body", default="")
    p = gh_sub.add_parser("update")
    p.add_argument("--repo")
    p.add_argument("--number", type=int, required=True)
    p.add_argument("--title")
    p.add_argument("--body")
    p.add_argument("--state")
    p = gh_sub.add_parser("comment")
    p.add_argument("--repo")
    p.add_argument("--number", type=int, required=True)
    p.add_argument("--body", required=True)

    lin = sub.add_parser("linear")
    lin_sub = lin.add_subparsers(dest="action", required=True)
    lin_sub.add_parser("list")
    p = lin_sub.add_parser("get")
    p.add_argument("--id", required=True)
    p = lin_sub.add_parser("create")
    p.add_argument("--title", required=True)
    p.add_argument("--body", default="")
    p.add_argument("--team")
    p = lin_sub.add_parser("update")
    p.add_argument("--id", required=True)
    p.add_argument("--title")
    p.add_argument("--body")
    p = lin_sub.add_parser("comment")
    p.add_argument("--id", required=True)
    p.add_argument("--body", required=True)
    return parser


def dispatch(args: argparse.Namespace) -> dict:
    if args.tracker == "github":
        if args.action == "list":
            return github_list(args.repo, args.state)
        if args.action == "get":
            return github_get(args.repo, args.number)
        if args.action == "create":
            return github_create(args.repo, args.title, args.body)
        if args.action == "update":
            return github_update(args.repo, args.number, args.title, args.body, args.state)
        if args.action == "comment":
            return github_comment(args.repo, args.number, args.body)
    if args.tracker == "linear":
        if args.action == "list":
            return linear_list()
        if args.action == "get":
            return linear_get(args.id)
        if args.action == "create":
            return linear_create(args.title, args.body, args.team)
        if args.action == "update":
            return linear_update(args.id, args.title, args.body)
        if args.action == "comment":
            return linear_comment(args.id, args.body)
    raise SystemExit(f"issues: unknown {args.tracker} {getattr(args, 'action', '')}")


def main(argv: list[str] | None = None) -> int:
    return _out(dispatch(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
