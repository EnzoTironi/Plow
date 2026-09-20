import json
import os
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/zoen/scripts"))
from google_account import Account, GoogleError, relay_url, verify_identity


def credential():
    return {"access_token": "fixture-access", "refresh_handle": "sealed-refresh",
            "expires_at": time.time() * 1000 + 3600000, "scopes": ["email"],
            "relay_url": "https://auth.example.com", "account": {"id": "owner", "email": "owner@example.com"}}


def test_private_persistence_and_status_never_disclose_tokens(tmp_path):
    account = Account(tmp_path)
    account.commit(credential(), None)
    assert os.stat(account.path).st_mode & 0o777 == 0o600
    assert os.stat(account.path.with_suffix(".lock")).st_mode & 0o777 == 0o600
    other_process = Account(tmp_path)
    assert other_process.token() == "fixture-access"
    status = json.dumps(other_process.status())
    assert "fixture-access" not in status and "sealed-refresh" not in status
    assert other_process.status()["account_verified"] is None


def test_reauthorization_cannot_overwrite_a_concurrent_account_change(tmp_path):
    account = Account(tmp_path)
    baseline = credential()
    account.commit(baseline, None)
    changed = {**baseline, "access_token": "newer-access"}
    account.commit(changed, baseline)
    with pytest.raises(GoogleError, match="account_changed"):
        account.commit(credential(), baseline)
    assert account.read() == changed


def test_refresh_uses_the_zoen_broker_and_preserves_account(tmp_path):
    account = Account(tmp_path)
    stale = {**credential(), "expires_at": 0}
    account.commit(stale, None)
    calls = []

    def http(method, url, body):
        calls.append((method, url, body))
        return {key: value for key, value in credential().items() if key not in {"account", "relay_url"}}

    assert Account(tmp_path).token(http) == "fixture-access"
    assert calls == [("POST", "https://auth.example.com/google/refresh", {"refresh_handle": "sealed-refresh"})]
    assert account.read()["account"] == stale["account"]


def test_failed_refresh_keeps_previous_credentials(tmp_path):
    account = Account(tmp_path)
    stale = {**credential(), "expires_at": 0}
    account.commit(stale, None)

    def denied(*args):
        raise GoogleError("google_http_401")

    with pytest.raises(GoogleError, match="401"):
        account.token(denied)
    assert account.read() == stale


@pytest.mark.parametrize("url", ["http://relay.example", "https://user:pass@relay.example", "https://relay.example/?token=x", "https://relay.example/path", "https://relay.example/#x"])
def test_relay_configuration_cannot_redirect_credentials(url):
    with pytest.raises(GoogleError):
        relay_url(url)


def test_identity_requires_verified_google_email():
    def http(method, url, *, bearer):
        assert url == "https://openidconnect.googleapis.com/v1/userinfo"
        assert bearer == "fixture-access"
        return {"sub": "owner", "email": "owner@example.com", "email_verified": True}

    assert verify_identity("fixture-access", http) == {"id": "owner", "email": "owner@example.com"}
    with pytest.raises(GoogleError, match="identity_unverified"):
        verify_identity("fixture-access", lambda *a, **kw: {"sub": "owner", "email": "owner@example.com"})


def test_redirect_never_forwards_credentials():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from google_account import request
    visited = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            visited.append(self.path)
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/elsewhere")
            self.end_headers()

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with pytest.raises(GoogleError, match="google_http_302"):
                request("GET", f"http://127.0.0.1:{server.server_port}/original", bearer="fixture-secret")
            assert visited == ["/original"]
        finally:
            server.shutdown()
            thread.join()


def test_reuse_checks_identity_without_new_consent(tmp_path):
    account = Account(tmp_path)
    account.commit(credential(), None)
    calls = []
    def http(method, url, **kwargs):
        calls.append(url)
        return {"sub": "owner", "email": "owner@example.com", "email_verified": True}
    assert account.verify(["email"], http) == credential()["account"]
    assert calls == ["https://openidconnect.googleapis.com/v1/userinfo"]


def test_missing_scope_requires_consent_without_reading_wrong_resource(tmp_path):
    account = Account(tmp_path)
    account.commit(credential(), None)
    def no_network(*args, **kwargs):
        raise AssertionError("no account read should be needed for a known missing scope")
    assert account.verify(["https://www.googleapis.com/auth/gmail.readonly"], no_network) is None


def test_reuse_network_failure_does_not_become_a_new_login(tmp_path):
    account = Account(tmp_path)
    account.commit(credential(), None)
    def offline(*args, **kwargs):
        raise GoogleError("google_connection_unavailable")
    with pytest.raises(GoogleError, match="connection_unavailable"):
        account.verify(["email"], offline)
    assert account.read()["account"] == credential()["account"]


def test_reuse_rejects_different_identity(tmp_path):
    account = Account(tmp_path)
    account.commit(credential(), None)
    def wrong_account(*args, **kwargs):
        return {"sub": "other", "email": "other@example.com", "email_verified": True}
    with pytest.raises(GoogleError, match="account_changed"):
        account.verify(["email"], wrong_account)


def test_revoked_access_needs_consent_and_broad_scope_satisfies_read(tmp_path):
    account = Account(tmp_path)
    account.commit({**credential(), "scopes": ["https://www.googleapis.com/auth/spreadsheets"]}, None)
    def owner(*args, **kwargs):
        return {"sub": "owner", "email": "owner@example.com", "email_verified": True}
    assert account.verify(["https://www.googleapis.com/auth/spreadsheets.readonly"], owner)
    def revoked(*args, **kwargs):
        raise GoogleError("google_http_401")
    assert account.verify([], revoked) is None
