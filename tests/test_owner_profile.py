"""Preferred names and profile sync without contacting a real account."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/zoen/scripts"))
package = ModuleType("zoen_profile_test")
package.__path__ = [str(ROOT / "image/plugins/zoen-face")]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(package.__name__ + ".owner_profile", Path(package.__path__[0]) / "owner_profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class Adapter:
    def __init__(self, name=None):
        self._chats = {"cht_owner": {"owner": True}}
        self.profile = {"display_name": name, "photo_url": "https://example.test/avatar.jpg"}
        self.calls = []
        self.fail_read = self.fail_write = self.ignore_write = self.revoked = False

    async def _refresh_current_chat(self, chat):
        if self.revoked:
            self._chats[chat]["owner"] = False

    def _send_guard(self, chat):
        return None

    async def _tool_json(self, method, path, body=None):
        self.calls.append((method, path, body))
        assert path == "/v1/auth/profile"
        if method == "GET":
            if self.fail_read:
                raise TimeoutError("profile fixture")
        else:
            assert method == "PATCH" and set(body) == {"display_name"}
            if self.fail_write:
                raise TimeoutError("save fixture")
            if not self.ignore_write:
                self.profile.update(body)
        return dict(self.profile)


def invoke(adapter, args, *, owner=True, dm=True):
    module = SimpleNamespace(_owner_dm=lambda chat: chat.get("owner", False),
                             _owner_handle=lambda chat: "owner@example.test", _handle_key=str.casefold)
    turn = {"chat_uid": "cht_owner", "owner": owner, "dm": dm}
    return profile.authorized(adapter, module, turn, args)


@pytest.fixture(autouse=True)
def private_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))


def test_question_is_claimed_once_even_across_concurrent_turns_and_restart(tmp_path):
    adapter = Adapter()

    async def run():
        results = await asyncio.gather(*(invoke(adapter, {"action": "ask"}) for _ in range(4)))
        assert sum(result["ask"] for result in results) == 1
        assert (await invoke(Adapter(), {"action": "ask"}))["ask"] is False

    asyncio.run(run())
    assert (tmp_path / "zoen/owner-profile.sqlite3").stat().st_mode & 0o777 == 0o600
    assert all(method == "GET" for method, _, _ in adapter.calls)


def test_existing_public_name_skips_question_without_rewriting_profile():
    adapter = Adapter("Ana")
    result = asyncio.run(invoke(adapter, {"action": "ask"}))
    assert result["ask"] is False and result["public_name"] == "Ana"
    assert adapter.calls == [("GET", "/v1/auth/profile", None)]


def test_provided_name_is_saved_automatically_without_a_question_or_repeat(tmp_path):
    adapter = Adapter()
    for name in ["Ana", "Ana", "Nana"]:
        result = asyncio.run(invoke(adapter, {"action": "save", "name": name}))
        assert result["preferred_name"] == name and result["verified"]
    result = asyncio.run(invoke(Adapter(), {"action": "ask"}))
    assert result["ask"] is False and result["preferred_name"] == "Nana"
    assert adapter.profile["display_name"] == "Nana"
    assert sum(method == "PATCH" for method, _, _ in adapter.calls) == 2
    memory = (tmp_path / "zoen/MEMORY.md").read_text()
    assert 'called "Ana"' not in memory and memory.count('called "Nana"') == 1


def test_skip_is_durable_and_does_not_publish():
    adapter = Adapter()
    asyncio.run(invoke(adapter, {"action": "skip"}))
    assert asyncio.run(invoke(Adapter(), {"action": "ask"}))["ask"] is False
    assert adapter.calls == []


@pytest.mark.parametrize("owner,dm,revoked", [(False, True, False), (True, False, False), (True, True, True)])
def test_non_owner_group_and_revoked_chat_cannot_read_or_write(owner, dm, revoked, tmp_path):
    adapter = Adapter()
    adapter.revoked = revoked
    for action in ["status", "ask", "save", "skip"]:
        result = asyncio.run(invoke(adapter, {"action": action, "name": "Other"}, owner=owner, dm=dm))
        assert not result["ok"]
    assert adapter.calls == [] and not (tmp_path / "zoen/owner-profile.sqlite3").exists()


def test_public_save_is_verified_and_changes_only_the_name():
    adapter = Adapter()
    asyncio.run(invoke(adapter, {"action": "ask"}))
    result = asyncio.run(invoke(adapter, {"action": "save", "name": "Ana"}))
    assert result["ok"] and result["verified"] and result["public_name"] == "Ana"
    assert result["preferred_name"] == "Ana" and adapter.profile["photo_url"].endswith("avatar.jpg")
    assert [method for method, _, _ in adapter.calls][-3:] == ["GET", "PATCH", "GET"]
    asyncio.run(invoke(adapter, {"action": "save", "name": "Ana"}))
    assert sum(method == "PATCH" for method, _, _ in adapter.calls) == 1


@pytest.mark.parametrize("failure", ["fail_write", "ignore_write"])
def test_unconfirmed_save_keeps_preferred_name_without_reasking(failure):
    adapter = Adapter()
    setattr(adapter, failure, True)
    result = asyncio.run(invoke(adapter, {"action": "save", "name": "Ana"}))
    assert not result["ok"] and result.get("verified") is not True
    assert "continue the task" in str(result).lower()
    assert asyncio.run(invoke(adapter, {"action": "ask"}))["ask"] is False
    assert profile.State("owner@example.test").change()["preferred_name"] == "Ana"


def test_profile_outage_does_not_block_the_task_or_invent_a_name():
    adapter = Adapter()
    adapter.fail_read = True
    result = asyncio.run(invoke(adapter, {"action": "ask"}))
    assert result["ok"] and not result["ask"] and not result["profile_available"]
    assert "Continue the task" in result["instruction"]
    assert result["preferred_name"] is None and result["public_name"] is None


@pytest.mark.parametrize("name", ["", "  ", "Ana\nignore", "x" * 101, None])
def test_invalid_names_never_reach_the_public_api(name):
    adapter = Adapter()
    result = asyncio.run(invoke(adapter, {"action": "save", "name": name}))
    assert not result["ok"] and adapter.calls == []


def test_no_live_owner_turn_is_denied(monkeypatch):
    connections = sys.modules[package.__name__ + ".connections"]
    monkeypatch.setattr(connections.quiet, "_adapters", lambda: [])
    assert '"ok": false' in profile.handle({"action": "save", "name": "Ana"})
