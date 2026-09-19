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
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import aiohttp

from statusline import draft

log = logging.getLogger("zoen-presence")
SILENCE = 2.0
MAX_WAIT = 3.0
HTTP_TIMEOUT = 3.0
REFRESH_TIMEOUT = 3.0
DRAFT_DELAY = .3
CLOSER = re.compile(r"^(?:valeu|thanks|thank you|thx|tks|obrigad[oa]|vlw|tmj|ty|gracias|merci)[\s.!❤️♥👍🙏]*$", re.I)
REQUEST = re.compile(r"\b(faz|faça|ajuda|pode|consegue|procura|pesquisa|organiza|lembra|cria|quero|preciso|please|can you|could you|help me|find|create|remind|schedule)\b", re.I)
SENSITIVE = re.compile(r"\b(morreu|morte|suicid\w*|câncer|cancer|abuso|acidente|died|dead|hurt|abuse|assault|kill)\b", re.I)


def reaction(text: str) -> str | None:
    if CLOSER.fullmatch(text.strip()):
        return "like"
    if REQUEST.search(text) and not SENSITIVE.search(text):
        return "like"
    return None


class Receipts:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS receipts (chat TEXT, message TEXT, state TEXT, updated REAL, PRIMARY KEY(chat, message))")
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
            row = db.execute("SELECT state FROM receipts WHERE chat=? AND message=?", (chat, message)).fetchone()
        return row[0] if row else None

    def claim(self, chat, messages):
        with self.connect() as db:
            rows = [(chat, m["uid"], "pending", time.time()) for m in messages]
            db.executemany("INSERT OR IGNORE INTO receipts VALUES (?,?,?,?)", rows)
            if db.total_changes != len(rows):
                db.rollback()
                return False
            return True

    def finish(self, chat, messages, state):
        with self.connect() as db:
            db.executemany("UPDATE receipts SET state=?, updated=? WHERE chat=? AND message=?",
                           [(state, time.time(), chat, m["uid"]) for m in messages])


class Presence:
    def __init__(self, adapter, module, receipts=None):
        self.adapter, self.module = adapter, module
        home = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes"))
        self.receipts = receipts or Receipts(home / "zoen" / "reception.db")
        self.home = home
        self.recent = {}
        self.bursts = {}
        self.tasks = set()
        self.waiting = {}

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
            burst = {"last": now, "messages": [], "changed": asyncio.Event(),
                     "http": aiohttp.ClientSession(base_url=self.module.BASE, headers=self.adapter.auth)}
            self.bursts[chat] = burst
            self.spawn(self.typing(chat))
            self.spawn(self.collect(chat, burst))
        burst["messages"].append(message)
        burst["last"] = now
        # Use the burst's quiet window for the permission read. Restart it on
        # new input so a long burst never authorizes against an old roster.
        if burst.get("refresh"):
            burst["refresh"].cancel()
        burst["refresh"] = asyncio.create_task(self.refresh(chat))
        if burst.get("draft"):
            burst["draft"].cancel()
        burst["draft"] = asyncio.create_task(self.opening(chat, list(burst["messages"]), burst["http"]))
        burst["changed"].set()
        self.waiting[(chat, message["uid"])] = asyncio.Event()

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

    async def opening(self, chat, messages, http):
        if all(CLOSER.fullmatch(m["body"].strip()) and not m.get("attachments") for m in messages):
            return None
        # Coalesce rapid frames before spending a model request. Both drafting
        # and authorization run during the normal two-second burst window.
        await asyncio.sleep(DRAFT_DELAY)
        return await draft(messages, http=http, home=self.home, recent=self.recent.get(chat, []))

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
            if await burst["refresh"]:
                await self.acknowledge(chat, messages, burst["draft"], burst["http"])
        finally:
            if self.bursts.get(chat) is burst:
                self.bursts.pop(chat)
            burst["refresh"].cancel()
            burst["draft"].cancel()
            await asyncio.gather(burst["refresh"], burst["draft"], return_exceptions=True)
            await burst["http"].close()
            for message in messages:
                ready = self.waiting.pop((chat, message["uid"]), None)
                if ready:
                    ready.set()
            log.info("reception %s", json.dumps({"chat": chat, "last_message": messages[-1]["uid"],
                "elapsed_ms": round((time.monotonic() - burst["last"]) * 1000), "messages": len(messages)}))

    async def acknowledge(self, chat, messages, opening, http):
        # collect() has awaited this burst's fresh membership read.
        if not self.module._owner_dm(self.adapter._chats.get(chat, {})):
            return
        if self.adapter._send_guard(chat) is not None:
            return
        if not self.receipts.claim(chat, messages):
            return
        text = "\n".join(m["body"] for m in messages)
        only_closer = all(CLOSER.fullmatch(m["body"].strip()) and not m.get("attachments") for m in messages)
        kind = "like" if only_closer else reaction(text)
        reaction_task = asyncio.create_task(
            self.post(chat, f"messages/{messages[-1]['uid']}/reactions", {"operation": "add", "type": kind}, http) if kind else self.no_post())
        try:
            body = await opening
            results = await asyncio.gather(
                self.post(chat, "messages", {"body": body, "format": "none"}, http) if body else self.no_post(),
                reaction_task,
            )
        finally:
            reaction_task.cancel()
            await asyncio.gather(reaction_task, return_exceptions=True)
        state = results[0] if body else results[1]
        if body and state in ("sent", "uncertain"):
            self.recent[chat] = (self.recent.get(chat, []) + [body])[-3:]
        if not body and not only_closer and state in ("sent", "uncertain"):
            state = "reacted" if state == "sent" else "reaction_uncertain"
        self.receipts.finish(chat, messages, state)
        log.info("receipt_result %s", json.dumps({"chat": chat, "last_message": messages[-1]["uid"],
                                                 "status": results[0], "reaction": results[1]}))

    async def no_post(self):
        return "skipped"

    async def post(self, chat, endpoint, payload, http):
        try:
            async with http.post(f"/v1/chats/{chat}/{endpoint}", json=payload,
                                 timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as response:
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

    async def annotate(self, event):
        key = (event.source.chat_id, event.message_id)
        ready = self.waiting.get(key)
        if ready:
            try:
                await asyncio.wait_for(ready.wait(), MAX_WAIT + REFRESH_TIMEOUT + HTTP_TIMEOUT)
            except TimeoutError:
                log.warning("reception wait expired; checking durable delivery state")
        state = self.receipts.state(*key)
        if state in ("reacted", "reaction_uncertain"):
            event.channel_prompt = (event.channel_prompt or "") + (
                "\n[Zoen reception]\nOnly a tapback was attempted; do not repeat the reaction. "
                "No status line was sent. Write your own brief, contextual opening before the work.")
            event.zoen_reception = state
            return
        if state not in ("sent", "uncertain", "pending"):
            return
        note = ("Reception already acknowledged this burst. Do not send another status line or tapback. "
                "Continue the actual request; acknowledgement is not completion.")
        if state != "sent":
            note = ("The reception acknowledgement may already have reached the owner. Do not replay it. "
                    "Continue the actual request and deliver its result.")
        event.channel_prompt = (event.channel_prompt or "") + "\n[Zoen reception]\n" + note
        event.zoen_reception = state


def install(adapter_cls, module, prepare_dispatch=None):
    if getattr(adapter_cls, "_zoen_presence", False):
        return
    original = adapter_cls._on_message
    handoff = adapter_cls._handoff_message

    @functools.wraps(original)
    async def on_message(self, message, chat):
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
