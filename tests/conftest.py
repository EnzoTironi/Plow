"""Unit tests stay on this machine.

A test that reaches the network is not a unit test: it depends on a live
service, and it can send a fixture credential somewhere real. Loopback is
allowed for in-process fixtures.
"""
from __future__ import annotations

import ipaddress
import socket

import pytest

_BLOCKED: list[str] = []
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def _loopback(host) -> bool:
    if host in ("localhost", "", None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_getaddrinfo(host, *args, **kwargs):
    if isinstance(host, bytes):
        host = host.decode()
    if not _loopback(host):
        _BLOCKED.append(str(host))
        raise OSError(f"network disabled in tests: {host}")
    return _getaddrinfo(host, *args, **kwargs)


def _guard(address) -> None:
    if isinstance(address, tuple) and address and not _loopback(address[0]):
        _BLOCKED.append(str(address[0]))
        raise OSError(f"network disabled in tests: {address[0]}")


def _guarded_connect(self, address):
    _guard(address)
    return _connect(self, address)


def _guarded_connect_ex(self, address):
    _guard(address)
    return _connect_ex(self, address)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    _BLOCKED.clear()
    yield
    # Code under test often swallows OSError, so a blocked call must still fail the test.
    assert not _BLOCKED, f"test tried to reach the network: {sorted(set(_BLOCKED))}"
