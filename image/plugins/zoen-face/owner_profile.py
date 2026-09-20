"""Ask for a missing preferred name once and keep the owner's profile in sync."""
import asyncio
import json
import os
import sqlite3

from context import zoen_dir
from memory import remember, revise
from .connections import owner_dm_tool


SCHEMA = {
    "name": "zoen_owner_profile",
    "description": "The owner's preferred name and Plow/Agent Index profile. Owner DM only. Ask reserves the one optional onboarding name question after checking for an existing name; ask only if ask=true. Save remembers the owner's supplied name and updates the profile, then verifies it. No separate confirmation is needed. Skip stops onboarding. Never guess a name, block their actual task, or repeat the question after a failure.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "ask", "save", "skip"]},
            "name": {"type": "string", "minLength": 1, "maxLength": 100},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


class State:
    def __init__(self, owner):
        folder = zoen_dir()
        folder.mkdir(parents=True, exist_ok=True)
        self.path, self.owner = folder / "owner-profile.sqlite3", owner
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS names (owner TEXT PRIMARY KEY, preferred_name TEXT, public_name TEXT, asked INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0)")
            db.execute("INSERT OR IGNORE INTO names(owner) VALUES (?)", (owner,))
        os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        return db

    def change(self, *, claim=False, **fields):
        if set(fields) - {"preferred_name", "public_name", "asked", "skipped"}:
            raise ValueError("unknown profile state field")
        with self.connect() as db:
            if fields:
                db.execute("UPDATE names SET " + ",".join(f"{key}=?" for key in fields) + " WHERE owner=?",
                           (*fields.values(), self.owner))
            ask = False
            if claim:
                result = db.execute("UPDATE names SET asked=1 WHERE owner=? AND asked=0 AND skipped=0 AND preferred_name IS NULL AND public_name IS NULL", (self.owner,))
                ask = result.rowcount == 1
            state = dict(db.execute("SELECT preferred_name, public_name, asked, skipped FROM names WHERE owner=?", (self.owner,)).fetchone())
        return {"ok": True, **state, **({"ask": ask} if claim else {})}

    def remember(self, name):
        previous = self.change()["preferred_name"]
        if previous != name:
            fact = f"Owner prefers to be called {json.dumps(name, ensure_ascii=False)}"
            old = f"Owner prefers to be called {json.dumps(previous, ensure_ascii=False)}"
            if not previous or not revise(old, fact).get("ok"):
                remember([fact])
        return self.change(preferred_name=name, asked=1)


async def read_profile(adapter, state):
    try:
        profile = await asyncio.wait_for(adapter._tool_json("GET", "/v1/auth/profile"), 4)
        if not isinstance(profile, dict) or "display_name" not in profile:
            raise ValueError("invalid profile response")
        name = profile["display_name"]
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValueError("invalid profile name")
        return {**state.change(public_name=name), "profile_available": True}
    except Exception:
        return {**state.change(), "profile_available": False, "ask": False,
                "instruction": "Continue the task. Profile lookup failed; do not guess or repeat onboarding."}


async def save(adapter, state, name):
    state.remember(name)
    before = await read_profile(adapter, state)
    if before.get("profile_available") and before.get("public_name") == name:
        return {**before, "verified": True}
    try:
        await asyncio.wait_for(adapter._tool_json("PATCH", "/v1/auth/profile", body={"display_name": name}), 4)
    except Exception:
        return {"ok": False, "preferred_name": name, "error": "Public profile save could not be confirmed. The preferred name is remembered; continue the task."}
    after = await read_profile(adapter, state)
    verified = after.get("profile_available") and after.get("public_name") == name
    return {**after, "ok": bool(verified), "verified": bool(verified),
            "instruction": "Saved and verified." if verified else "Public save is unconfirmed. Continue the task; do not ask their name again."}


async def authorized(adapter, module, turn, args):
    chat = turn["chat_uid"]
    await asyncio.wait_for(adapter._refresh_current_chat(chat), 4)
    if not turn.get("owner") or not turn.get("dm") or not module._owner_dm(adapter._chats.get(chat, {})) or adapter._send_guard(chat) is not None:
        return {"ok": False, "error": "Profile changes require the owner's current private chat."}
    owner = module._owner_handle(adapter._chats[chat])
    if not owner:
        return {"ok": False, "error": "Owner identity is unavailable."}
    action = args.get("action")
    if action not in {"status", "ask", "save", "skip"}:
        return {"ok": False, "error": "Unknown profile action."}
    if action == "save":
        name = args.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(c) < 32 for c in name):
            return {"ok": False, "error": "Use the owner's exact single-line name, at most 100 characters."}
        args = {**args, "name": name.strip()}
    state = State(module._handle_key(owner))
    if action == "skip":
        return state.change(skipped=1, asked=1)
    if action == "save":
        return await save(adapter, state, args["name"])
    current = state.change()
    if action == "ask" and (current["preferred_name"] or current["asked"] or current["skipped"]):
        return {**current, "ask": False}
    profile = await read_profile(adapter, state)
    return state.change(claim=True) if action == "ask" and profile["profile_available"] else profile


def handle(args, **_kwargs):
    return owner_dm_tool(args, authorized, "profile")
