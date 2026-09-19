import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/zoen/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("zoen_connect", SCRIPTS / "connect.py")
connect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connect)


def test_connect_returns_short_lived_link_without_bearer(monkeypatch):
    monkeypatch.setenv("PLOW_AGENT_TOKEN", "test-bearer")
    monkeypatch.delenv("PLOW_CONNECTOR_TOKEN", raising=False)
    monkeypatch.setenv("PLOW_API_BASE", "https://api.plow.co")
    calls = []

    def http(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "body": {"code": "short+code", "unexpected": "secret"}}

    result = connect.connection("connect", "google", http)
    assert result["connect_url"] == "https://api.plow.co/v1/connectors/gmail/connect?code=short%2Bcode"
    assert "test-bearer" not in str(result) and "secret" not in str(result)
    assert result["connected"] is False
    assert calls[0][0][0] == "POST"


def test_failed_status_is_not_disconnected(monkeypatch):
    monkeypatch.setenv("PLOW_AGENT_TOKEN", "test-bearer")
    result = connect.connection("status", "slack", lambda *a, **kw: {"ok": False, "status": 403})
    assert not result["ok"]
    assert "connected" not in result


def test_unsupported_connector_does_not_make_request():
    def refused(*a, **kw):
        raise AssertionError("unexpected request")
    assert not connect.connection("connect", "arbitrary-server", refused)["ok"]
