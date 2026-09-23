"""Bounded reception for the owner's DM, independent of model and media latency.

Plow still owns input ordering, authorization and execution. This observer only
acknowledges accepted input. A durable send claim prevents replay after an
ambiguous POST; it is never a checkpoint for the user's actual work.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import aiohttp

import face
from credits import clear_told
from statusline import draft

log = logging.getLogger("zoen-presence")
SILENCE = 2.0
DEADLINE = 5.0
HTTP_TIMEOUT = 3.0
REFRESH_TIMEOUT = 3.0
DRAFT_DELAY = .15


class Receipts:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS receipts (chat TEXT, message TEXT, state TEXT, updated REAL, PRIMARY KEY(chat, message))")
            columns = {row[1] for row in db.execute("PRAGMA table_info(receipts)")}
            for effect in ("status", "reaction"):
                if effect not in columns:
                    db.execute(f"ALTER TABLE receipts ADD COLUMN {effect} TEXT")
            # Legacy records cannot establish which effect reached the phone.
            # Seal both against replay; fresh messages get independent outcomes.
            db.execute("UPDATE receipts SET status='uncertain', reaction='uncertain' WHERE status IS NULL")
        os.chmod(path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=0.1)
        try:
            with db:
                yield db
        finally:
            db.close()

    def state(self, chat, message):
        with self.connect() as db:
            row = db.execute("SELECT status, reaction FROM receipts WHERE chat=? AND message=?", (chat, message)).fetchone()
        return dict(zip(("status", "reaction"), row)) if row else None

    def claim(self, chat, messages):
        with self.connect() as db:
            rows = [(chat, m["uid"], "pending", time.time(), "pending", "pending") for m in messages]
            db.executemany("INSERT OR IGNORE INTO receipts (chat,message,state,updated,status,reaction) VALUES (?,?,?,?,?,?)", rows)
            if db.total_changes != len(rows):
                db.rollback()
                return False
            return True

    def finish(self, chat, messages, effect, state):
        if effect not in {"status", "reaction"}:
            raise ValueError("unknown reception effect")
        with self.connect() as db:
            db.executemany(f"UPDATE receipts SET {effect}=?, state='recorded', updated=? WHERE chat=? AND message=?",
                           [(state, time.time(), chat, m["uid"]) for m in messages])


class Presence:
    def __init__(self, adapter, module, receipts=None):
        self.adapter, self.module = adapter, module
        home = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes"))
        self.receipts = receipts or Receipts(home / "zoen" / "reception.db")
        self.home = home
        self.voiced = face.voice_exists()
        self.recent = {}
        self.context = {}
        self.bursts = {}
        self.tasks = set()
        self.waiting = {}
        self.eyed = set()

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.completed)
        return task

    def completed(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("reception failed: %s", type(task.exception()).__name__)

    def accept(self, message, chat):
        if message["body"].startswith("/") or self.receipts.state(chat, message["uid"]):
            return
        now = time.monotonic()
        log.info("received %s", json.dumps({"chat": chat, "message": message["uid"],
                                           "provider_created_at": message.get("created_at"),
                                           "received_at": time.time()}))
        burst = self.bursts.get(chat)
        if burst is None:
            for (pending_chat, _), pending in self.waiting.items():
                if pending_chat == chat:
                    pending["closed"] = True
            burst = {"last": now, "messages": [], "closed": False, "context": self.context.get(chat, []), "changed": asyncio.Event(),
                     "http": aiohttp.ClientSession(base_url=self.module.BASE, headers=self.adapter.auth)}
            self.bursts[chat] = burst
            self.spawn(self.typing(chat))
            self.spawn(self.collect(chat, burst))
        burst["messages"].append(message)
        self.context[chat] = (burst["context"] + [m["body"][:500] for m in burst["messages"]])[-6:]
        burst["last"] = now
        burst["deadline"] = now + DEADLINE
        # Use the burst's quiet window for the permission read. Restart it on
        # new input so a long burst never authorizes against an old roster.
        if burst.get("refresh"):
            burst["refresh"].cancel()
        burst["refresh"] = asyncio.create_task(self.refresh(chat))
        if burst.get("draft"):
            burst["draft"].cancel()
        burst["draft"] = asyncio.create_task(self.opening(chat, burst))
        burst["changed"].set()
        self.waiting[(chat, message["uid"])] = burst

    async def typing(self, chat):
        try:
            await asyncio.wait_for(self.adapter.send_typing(chat), HTTP_TIMEOUT)
        except (TimeoutError, OSError):
            log.debug("typing unavailable")

    async def refresh(self, chat):
        try:
            await asyncio.wait_for(self.adapter._refresh_current_chat(chat), REFRESH_TIMEOUT)
            return True
        except (TimeoutError, OSError, RuntimeError, aiohttp.ClientError) as error:
            log.warning("reception permission read failed: %s", type(error).__name__)
            return False

    async def opening(self, chat, burst):
        if not self.voiced:
            return {}
        messages = list(burst["messages"])
        await asyncio.sleep(DRAFT_DELAY)
        return await draft(messages, http=burst["http"], home=self.home, recent=self.recent.get(chat, []),
                           context=burst["context"])

    def answer_delivered(self, chat, message):
        burst = self.waiting.get((chat, message))
        if burst is not None:
            burst["closed"] = True

    async def collect(self, chat, burst):
        messages = burst["messages"]
        try:
            while True:
                delay = burst["last"] + SILENCE - time.monotonic()
                if delay <= 0:
                    break
                burst["changed"].clear()
                try:
                    await asyncio.wait_for(burst["changed"].wait(), delay)
                except TimeoutError:
                    break
            self.bursts.pop(chat, None)
            if await burst["refresh"] and not burst["closed"]:
                await self.acknowledge(chat, burst)
        finally:
            if self.bursts.get(chat) is burst:
                self.bursts.pop(chat)
            burst["refresh"].cancel()
            burst["draft"].cancel()
            await asyncio.gather(burst["refresh"], burst["draft"], return_exceptions=True)
            await burst["http"].close()
            for message in messages:
                self.waiting.pop((chat, message["uid"]), None)
            log.info("reception %s", json.dumps({"chat": chat, "last_message": messages[-1]["uid"],
                "elapsed_ms": round((time.monotonic() - burst["last"]) * 1000), "messages": len(messages)}))

    async def acknowledge(self, chat, burst):
        messages = burst["messages"]
        if not self.module._owner_dm(self.adapter._chats.get(chat, {})) or self.adapter._send_guard(chat) is not None:
            return
        if not self.receipts.claim(chat, messages):
            return
        opening = await burst["draft"] or {}
        body = opening.get("line")
        # The eye goes out when the model is called. This draft does not pick a tapback.
        status, reaction = await asyncio.gather(
            self.deliver(chat, burst, "status", "messages", {"body": body, "format": "none"} if body else None),
            self.deliver(chat, burst, "reaction", f"messages/{messages[-1]['uid']}/reactions", None),
        )
        if body and status in {"sent", "uncertain"}:
            self.recent[chat] = (self.recent.get(chat, []) + [body])[-3:]
        log.info("receipt_result %s", json.dumps({"chat": chat, "last_message": messages[-1]["uid"],
                                                 "status": status, "reaction": reaction}))

    async def deliver(self, chat, burst, effect, endpoint, payload):
        state = "skipped"
        if payload and not burst["closed"] and time.monotonic() < burst["deadline"]:
            # A crash after this durable claim has an ambiguous outcome for
            # this effect only. Never replay an uncertain POST automatically.
            self.receipts.finish(chat, burst["messages"], effect, "uncertain")
            state = await self.post(chat, endpoint, payload, burst["http"], burst["deadline"])
        self.receipts.finish(chat, burst["messages"], effect, state)
        return state

    async def post(self, chat, endpoint, payload, http, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "skipped"
        try:
            async with http.post(f"/v1/chats/{chat}/{endpoint}", json=payload,
                                 timeout=aiohttp.ClientTimeout(total=min(HTTP_TIMEOUT, remaining))) as response:
                if response.status in (408, 424) or response.status >= 500:
                    return "uncertain"
                if response.status >= 400:
                    log.warning("reception POST rejected: endpoint=%s status=%s", endpoint, response.status)
                    return "failed"
                if endpoint == "messages":
                    result = await response.json()
                    if not isinstance(result, dict) or not result.get("uid"):
                        return "uncertain"
                    log.info("status_accepted %s", json.dumps({"chat": chat, "message": result["uid"],
                                                               "accepted_at": time.time()}))
                else:
                    log.info("reaction_accepted %s", json.dumps({"chat": chat, "endpoint": endpoint,
                                                                 "accepted_at": time.time()}))
                return "sent"
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return "uncertain"

    async def notice_model(self, event):
        """Typing as the model turn starts. Once per message.

        A custom emoji on this line is written out as a text bubble. The eye
        stays on WhatsApp, where it is a reaction.
        """
        if getattr(event, "internal", False) or getattr(event, "zoen_whatsapp", None):
            return
        source = getattr(event, "source", None)
        chat = str(getattr(source, "chat_id", "") or "")
        message = str(getattr(event, "message_id", "") or "")
        if not chat.startswith("cht_") or not message.startswith("msg_"):
            return
        if not self.module._owner_dm(self.adapter._chats.get(chat, {})):
            return
        if (chat, message) in self.eyed:
            return
        self.eyed.add((chat, message))
        log.info("zoen-face typing")
        await self.typing(chat)

    async def annotate(self, event):
        if getattr(event, "internal", False):
            return
        key = (event.source.chat_id, event.message_id)
        state = self.receipts.state(*key)
        if key not in self.waiting and state is None:
            return
        event.zoen_reception = state or {"status": "pending", "reaction": "pending"}
        event.channel_prompt = (event.channel_prompt or "") + (
            "\n<reception>\nTyping is already on. Do not send a reaction. "
            "Reception owns this burst's opening. "
            "Continue the actual work immediately; do not repeat the opening or reaction. "
            "An acknowledgement is not completion. Owner bubbles only go through "
            "zoen_imessage; leftover prose is not delivered. Never skip that tool. "
            "Send the reply as text. "
            "Reception outcomes: " + json.dumps(event.zoen_reception) + "\n</reception>")


def install(adapter_cls, module, prepare_dispatch=None):
    if getattr(adapter_cls, "_zoen_presence", False):
        return
    original = adapter_cls._on_message
    handoff = adapter_cls._handoff_message

    @functools.wraps(original)
    async def on_message(self, message, chat):
        sender = message.get("sender") or {}
        if sender.get("type") == "member" and sender.get("role") == "owner":
            clear_told(channel="imessage")
        seen = (chat, message["uid"]) in self._seen
        await original(self, message, chat)
        accepted = (chat, message["uid"]) in self._seen
        sender = message.get("sender", {})
        if seen or not accepted or sender.get("type") != "member" or sender.get("role") != "owner":
            return
        if chat not in self.chat_uids or not module._owner_dm(self._chats.get(chat, {})):
            return
        try:
            if not hasattr(self, "_zoen_reception"):
                self._zoen_reception = Presence(self, module)
            self._zoen_reception.accept(message, chat)
        except (OSError, sqlite3.Error):
            log.exception("reception unavailable; input remains queued")

    @functools.wraps(handoff)
    async def handoff_message(self, event):
        if not hasattr(self, "_zoen_reception"):
            self._zoen_reception = Presence(self, module)
        try:
            await self._zoen_reception.notice_model(event)
        except (OSError, sqlite3.Error, aiohttp.ClientError):
            log.exception("eye unavailable; the reply still runs")
        if hasattr(self, "_zoen_reception"):
            try:
                await self._zoen_reception.annotate(event)
            except (OSError, sqlite3.Error):
                log.exception("reception state unavailable; preserving input handoff")
        # Hermes' policy hook is synchronous. Compute its result off the receive
        # loop, then let that hook apply it in the normal authorization pipeline.
        if prepare_dispatch is not None:
            try:
                event.zoen_dispatch_result = await asyncio.to_thread(prepare_dispatch, event)
            except Exception:
                log.exception("dispatch preparation failed; retaining the native policy hook")
        return await handoff(self, event)

    adapter_cls._on_message = on_message
    adapter_cls._handoff_message = handoff_message
    adapter_cls._zoen_presence = True
