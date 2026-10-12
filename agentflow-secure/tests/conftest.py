"""Tests run without a key and without the network: a paid call is impossible even by accident."""
import socket

import pytest


@pytest.fixture(autouse=True)
def _no_key_no_network(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def _blocked(*args, **kwargs):
        raise RuntimeError("Network is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
