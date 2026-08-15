"""Tests for loading the redis plugin into a Xyberos app."""

from __future__ import annotations

import pytest
from xyberos import create_app

from xyberos_redis import RedisPlugin


@pytest.fixture()
def client():
    return pytest.importorskip("fakeredis").FakeStrictRedis()


def test_plugin_conforms_to_contract():
    plugin = RedisPlugin()
    assert plugin.name == "redis"
    assert callable(plugin.register) and callable(plugin.unregister)


def test_plugin_registers_services(client):
    app = create_app()
    app.load_plugin(RedisPlugin(client=client, key_prefix="test"))
    assert "redis_client" in app.registry.names
    assert "redis_vector" in app.registry.names
    assert "redis_memory" in app.registry.names
    assert "redis_cache" in app.registry.names

    vector = app.resolve("redis_vector")
    vector.upsert("ns", "a", [1.0, 0.0, 0.0, 0.0], {"text": "alpha"})
    assert vector.query("ns", [1.0, 0.0, 0.0, 0.0], top_k=1)[0].payload["text"] == "alpha"

    memory = app.resolve("redis_memory")
    memory.store(type("Ctx", (), {"prompt": "q", "response": "a", "metadata": {}})())
    assert memory.retrieve(type("Ctx", (), {})())[0].prompt == "q"

    app.unload_plugin("redis")


def test_replace_defaults(client):
    app = create_app()
    app.load_plugin(RedisPlugin(client=client, key_prefix="test", replace_defaults=True))
    assert app.resolve("memory").__class__.__name__ == "RedisMemory"
    assert app.resolve("vector_store").__class__.__name__ == "RedisVectorStore"
    app.unload_plugin("redis")
