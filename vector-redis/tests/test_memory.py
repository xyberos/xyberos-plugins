"""Tests for RedisMemory — unit + parity with SqliteMemory semantics."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from xyberos.memory import MemoryEntry, SqliteMemory

from xyberos_redis import RedisMemory


@pytest.fixture()
def client():
    return pytest.importorskip("fakeredis").FakeStrictRedis()


@pytest.fixture()
def memory(client):
    return RedisMemory(client=client)


def _ctx(prompt="hello", response="hi", metadata=None, plan=None, error=None):
    return SimpleNamespace(
        prompt=prompt, response=response, metadata=metadata, plan=plan, error=error
    )


def test_store_and_retrieve_in_order(memory):
    memory.store(_ctx(prompt="first", response="one"))
    memory.store(_ctx(prompt="second", response="two"))
    entries = memory.retrieve(_ctx())
    assert [e.prompt for e in entries] == ["first", "second"]
    assert entries[0].response == "one"
    assert entries[1].response == "two"


def test_metadata_round_trip(memory):
    memory.store(_ctx(prompt="q", response="a", metadata={"user": "baltz"}))
    entry = memory.retrieve(_ctx())[0]
    assert entry.metadata == {"user": "baltz"}


def test_clear(memory):
    memory.store(_ctx())
    memory.clear()
    assert memory.retrieve(_ctx()) == []


def test_parity_with_sqlite_memory(client):
    """RedisMemory and SqliteMemory must expose the same observable behavior."""
    redis_mem = RedisMemory(client=client)
    sqlite_mem = SqliteMemory(":memory:")
    ctx = _ctx(prompt="q", response="a", metadata={"k": "v"}, plan={"step": 1})

    redis_mem.store(ctx)
    sqlite_mem.store(ctx)

    redis_entries = redis_mem.retrieve(_ctx())
    sqlite_entries = sqlite_mem.retrieve(_ctx())

    assert len(redis_entries) == len(sqlite_entries) == 1
    assert redis_entries[0].prompt == sqlite_entries[0].prompt == "q"
    assert redis_entries[0].response == sqlite_entries[0].response == "a"
    assert redis_entries[0].metadata == sqlite_entries[0].metadata == {"k": "v"}
    assert redis_entries[0].plan == sqlite_entries[0].plan == {"step": 1}
    assert redis_entries[0].created_at  # both record a timestamp
