"""Tests for loading the queues plugin into a Xyberos app."""

from __future__ import annotations

import pytest
from xyberos import create_app

from xyberos_queues import QueuesPlugin


@pytest.fixture()
def redis_client():
    return pytest.importorskip("fakeredis").FakeStrictRedis()


def test_plugin_registers_and_executes(redis_client):
    app = create_app()
    app.load_plugin(QueuesPlugin(provider="redis", client=redis_client))
    assert "queue_publish" in app.tools.names
    assert "queue_poll" in app.tools.names

    app.tools.execute("queue_publish", None, topic="jobs", message="do work")
    assert app.tools.execute("queue_poll", None, topic="jobs") == "do work"

    app.unload_plugin("queues")
    assert "queue_publish" not in app.tools.names


def test_unknown_provider_raises():
    import pytest as _pytest

    with _pytest.raises(ValueError, match="unknown queue provider"):
        QueuesPlugin(provider="bogus").message_queue()
