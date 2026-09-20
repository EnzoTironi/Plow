"""Private Google account state. The OAuth app secret never enters the agent."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class GoogleError(RuntimeError):
    """Safe code only; HTTP bodies and credentials never enter errors."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(method, url, body=None, bearer=None):
    headers = {"Content-Type": "application/json", "User-Agent": "Zoen/1.0 (+https://github.com/EnzoTironi/Plow)"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(url, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as result:
            data = json.loads(result.read(65537))
            if not isinstance(data, dict):
                raise GoogleError("google_response_invalid")
            return data
    except urllib.error.HTTPError as exc:
        raise GoogleError(f"google_http_{exc.code}") from None
    except (OSError, ValueError):
        raise GoogleError("google_connection_unavailable") from None


def relay_url(value):
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path.rstrip("/")):
        raise GoogleError("google_relay_configuration_invalid")
    return value.rstrip("/")


class Account:
    def __init__(self, home=None):
        self.path = Path(home or os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "zoen" / "google.json"

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def read(self):
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return None

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=".google-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(data, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def commit(self, data, baseline):
        with self.locked():
            if self.read() != baseline:
                raise GoogleError("google_account_changed_during_login")
            self.save(data)

    def token(self, http=request, *, force=False):
        with self.locked():
            data = self.read()
            if not data:
                raise GoogleError("google_not_connected")
            if force or data["expires_at"] <= time.time() * 1000 + 60000:
                refreshed = http("POST", relay_url(data["relay_url"]) + "/google/refresh",
                                 {"refresh_handle": data["refresh_handle"]})
                validate_tokens(refreshed)
                data.update(refreshed)
                self.save(data)
            return data["access_token"]

    def status(self):
        data = self.read()
        return {"credentials_saved": bool(data), "account": data.get("account") if data else None,
                "auth_mode_at_consent": data.get("auth_mode") if data else None,
                "scopes": data.get("scopes", []) if data else [], "account_verified": None,
                "status": "credentials_saved" if data else "not_started",
                "instruction": "Saved state is not a live access check. Verify with a small requested read."}

    def verify(self, required_scopes, http=request):
        baseline = self.read()
        if not baseline:
            return None
        scopes = set(baseline.get("scopes", []))
        if any(scope not in scopes and scope.removesuffix(".readonly") not in scopes for scope in required_scopes):
            return None
        try:
            identity = verify_identity(self.token(http), http)
        except GoogleError as exc:
            if str(exc) == "google_http_401":
                return None  # An explicit connect request may renew a revoked grant.
            raise
        current = self.read()
        if (current is None or identity["id"] != baseline.get("account", {}).get("id")
                or current.get("account", {}).get("id") != identity["id"]
                or set(current.get("scopes", [])) != scopes):
            raise GoogleError("google_account_changed_during_check")
        return identity


def validate_tokens(data):
    if not (isinstance(data.get("access_token"), str) and data["access_token"]
            and isinstance(data.get("refresh_handle"), str) and data["refresh_handle"]
            and isinstance(data.get("expires_at"), (float, int)) and data["expires_at"] > time.time() * 1000
            and isinstance(data.get("scopes"), list)):
        raise GoogleError("google_credentials_invalid")


def verify_identity(token, http=request):
    identity = http("GET", "https://openidconnect.googleapis.com/v1/userinfo", bearer=token)
    if not identity.get("sub") or not identity.get("email") or identity.get("email_verified") is not True:
        raise GoogleError("google_identity_unverified")
    return {"id": identity["sub"], "email": identity["email"]}
