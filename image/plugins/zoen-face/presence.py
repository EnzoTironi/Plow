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

from credits import language as prior_language
from lang import detect_language

log = logging.getLogger("zoen-presence")
SILENCE = 2.0
MAX_WAIT = 3.0
HTTP_TIMEOUT = 1.4
REFRESH_TIMEOUT = 0.5
LANGUAGE_TIMEOUT = 0.2
ACK = {
    "pt": "tô nisso", "en": "on it", "es": "voy con eso",
    "fr": "je m’en occupe", "de": "ich kümmere mich", "it": "ci penso io",
    "nl": "ik kijk ernaar", "ja": "確認するね", "ko": "확인할게",
    "zh": "我看看", "ru": "сейчас посмотрю", "ar": "سأرى ذلك",
}
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
            burst = {"last": now, "messages": [], "changed": asyncio.Event()}
            self.bursts[chat] = burst
            self.spawn(self.typing(chat))
            self.spawn(self.collect(chat, burst))
        burst["messages"].append(message)
        burst["last"] = now
        burst["changed"].set()
        self.waiting[(chat, message["uid"])] = asyncio.Event()

    async def typing(self, chat):
        try:
            await asyncio.wait_for(self.adapter.send_typing(chat), HTTP_TIMEOUT)
        except (TimeoutError, OSError):
            log.debug("typing unavailable")

    async def collect(self, chat, burst):
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
        messages = burst["messages"]
        try:
            await self.acknowledge(chat, messages)
        finally:
            for message in messages:
                ready = self.waiting.pop((chat, message["uid"]), None)
                if ready:
                    ready.set()
            log.info("reception %s", json.dumps({"chat": chat, "last_message": messages[-1]["uid"],
                "elapsed_ms": round((time.monotonic() - burst["last"]) * 1000), "messages": len(messages)}))

    async def acknowledge(self, chat, messages):
        # Refresh before sending: cached membership alone is not authority.
        await asyncio.wait_for(self.adapter._refresh_current_chat(chat), REFRESH_TIMEOUT)
        if not self.module._owner_dm(self.adapter._chats.get(chat, {})):
            return
        if self.adapter._send_guard(chat) is not None:
            return
        if not self.receipts.claim(chat, messages):
            return
        text = "\n".join(m["body"] for m in messages)
        only_closer = all(CLOSER.fullmatch(m["body"].strip()) and not m.get("attachments") for m in messages)
        kind = "like" if only_closer else reaction(text)
        body = None
        if not only_closer:
            language = prior_language()
            try:
                language = await asyncio.wait_for(
                    asyncio.to_thread(detect_language, text[:4096], language), LANGUAGE_TIMEOUT)
            except TimeoutError:
                log.debug("language detection timed out; using the owner's prior language")
            body = ACK.get(language, "on it")
        results = await asyncio.gather(
            self.post(chat, "messages", {"body": body}) if body else self.no_post(),
            self.post(chat, f"messages/{messages[-1]['uid']}/reactions", {"operation": "add", "type": kind}) if kind else self.no_post(),
        )
        state = results[0] if body else results[1]
        self.receipts.finish(chat, messages, state)

    async def no_post(self):
        return "skipped"

    async def post(self, chat, endpoint, payload):
        import aiohttp
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as http:
                async with http.post(f"{self.module.BASE}/v1/chats/{chat}/{endpoint}", json=payload, headers=self.adapter.auth) as response:
                    if response.status in (408, 424) or response.status >= 500:
                        return "uncertain"
                    if response.status >= 400:
                        return "failed"
                    if endpoint == "messages":
                        result = await response.json()
                        if not isinstance(result, dict) or not result.get("uid"):
                            return "uncertain"
                        log.info("status_accepted %s", json.dumps({"chat": chat, "message": result["uid"],
                                                                   "accepted_at": time.time()}))
                    return "sent"
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return "uncertain"

    async def annotate(self, event):
        key = (event.source.chat_id, event.message_id)
        ready = self.waiting.get(key)
        if ready:
            try:
                await asyncio.wait_for(ready.wait(), MAX_WAIT + REFRESH_TIMEOUT + LANGUAGE_TIMEOUT + HTTP_TIMEOUT)
            except TimeoutError:
                log.warning("reception wait expired; checking durable delivery state")
        state = self.receipts.state(*key)
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
