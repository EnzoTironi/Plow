"""Image integration: real gateway modules and Google client; simulated provider only."""
import asyncio
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path[:0] = ["/opt/hermes", "/opt/plow/zoen"]
from google_account import Account


class Relay:
    def __init__(self):
        self.base, self.secret, self.path = "https://auth.example.com", "fixture-poll", None
        self.state, self.finished = None, False

    async def request(self, method, path, body, **kwargs):
        if path == "/google/flows":
            assert body["capabilities"] == ["calendar_read"]
            self.state, self.challenge = body["state"], body["code_challenge"]
            return {"authorization_url": "https://accounts.google.com/fixture", "expires_at": time.time() * 1000 + 300000}
        assert path == f"/google/flows/{hashlib.sha256(self.state.encode()).hexdigest()}/exchange"
        import base64
        assert base64.urlsafe_b64encode(hashlib.sha256(body["code_verifier"].encode()).digest()).decode().rstrip("=") == self.challenge
        return {"access_token": "fixture-google-access", "refresh_handle": "fixture-sealed-refresh",
                "expires_at": time.time() * 1000 + 3600000, "scopes": ["email", "https://www.googleapis.com/auth/calendar.events.readonly"]}

    async def poll(self):
        return {"status": "ready", "callback": {"state": self.state, "code": "fixture-code"}}

    async def finish(self, *, consumed=False):
        self.finished = consumed


async def verify(home):
    os.environ["HERMES_HOME"] = home
    shutil.copy("/opt/hermes/plow-seed/config.yaml", Path(home) / "config.yaml")
    from hermes_cli.plugins import get_plugin_manager
    manager = get_plugin_manager()
    manager.discover_and_load()
    plugin = manager._plugins["zoen-face"].module
    from importlib import import_module
    google = import_module(plugin.__name__ + ".google_connections")
    events = []

    async def notify(adapter, module, chat, name, details):
        assert chat == "owner-chat" and name == "google"
        events.append(details)

    async def refresh(chat):
        assert chat == "owner-chat"

    adapter = SimpleNamespace(_refresh_current_chat=refresh, _chats={"owner-chat": {"owner": True}}, _send_guard=lambda chat: None)
    module = SimpleNamespace(_owner_dm=lambda chat: chat.get("owner"))
    identity = {"id": "owner-google-id", "email": "owner@example.com"}
    job = google.GoogleJob(adapter, module, "owner-chat", home, "https://auth.example.com", {"capabilities": ["calendar_read"]})
    job.relay = Relay()
    with patch.object(google.mcp_connections, "notify", notify), patch.object(google, "verify_identity", return_value=identity):
        await job.run()
    assert job.status == "credentials_saved" and job.relay.finished
    assert len(events) == 2 and "Google identity verified" in events[1]
    assert all("fixture-google-access" not in text and "fixture-sealed-refresh" not in text for text in events)
    account = Account(home)
    baseline = account.read()
    assert baseline["account"] == identity and account.path.stat().st_mode & 0o777 == 0o600

    # Adding Calendar permission must not silently switch the account.
    other = google.GoogleJob(adapter, module, "owner-chat", home, "https://auth.example.com", {"capabilities": ["calendar_read"]})
    other.relay = Relay()
    with patch.object(google.mcp_connections, "notify", notify), patch.object(google, "verify_identity", return_value={"id": "different", "email": "different@example.com"}):
        await other.run()
    assert other.status == "authorization_failed" and account.read() == baseline

    revoked = google.GoogleJob(adapter, module, "owner-chat", home, "https://auth.example.com", {"capabilities": ["calendar_read"]})
    revoked.relay = Relay()
    adapter._chats["owner-chat"]["owner"] = False
    with patch.object(google.mcp_connections, "notify", notify), patch.object(google, "verify_identity", return_value=identity):
        await revoked.run()
    assert revoked.status == "authorization_failed" and account.read() == baseline
    adapter._chats["owner-chat"]["owner"] = True

    # Reuse the actual bundled Hermes command and Google API client. Intercept
    # only the HTTP boundary so this test never reads a real user's calendar.
    import httplib2
    import google_workspace
    calls = []

    def google_http(self, uri, method="GET", body=None, headers=None, **kwargs):
        assert uri.startswith("https://www.googleapis.com/calendar/v3/calendars/primary/events?")
        assert method == "GET" and headers["authorization"] == "Bearer fixture-google-access"
        calls.append(uri)
        return httplib2.Response({"status": "200", "content-type": "application/json"}), b'{"items":[{"id":"fixture-event","summary":"Fixture event"}]}'

    output = io.StringIO()
    with patch.object(sys, "argv", ["google_workspace.py", "calendar", "list"]), patch.object(httplib2.Http, "request", google_http), redirect_stdout(output):
        google_workspace.main()
    assert len(calls) == 1 and json.loads(output.getvalue())[0]["id"] == "fixture-event"
    print(json.dumps({"google_independent_oauth": True, "pkce": True, "private_persistence": True,
                      "account_switch_guard": True, "native_hermes_calendar_command": True,
                      "owner_rechecked_before_commit": True,
                      "real_google_account": False}))


with tempfile.TemporaryDirectory() as home:
    asyncio.run(verify(home))
