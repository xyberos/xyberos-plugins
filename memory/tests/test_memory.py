from __future__ import annotations

import asyncio

import pytest
from xyberos_memory import ConversationMemory, MemoryScope

from xyberos.ai import Message, Role, ToolCall
from xyberos.database import SqliteSettings, open_database


def test_messages_and_scoped_facts_persist_and_clear() -> None:
    async def scenario() -> None:
        database = await open_database(
            SqliteSettings(path=":memory:", journal_mode="MEMORY", synchronous="NORMAL")
        )
        try:
            memory = ConversationMemory(database)
            await memory.initialize()
            scope = MemoryScope("conversation", "one")
            await memory.append_message(
                scope,
                Message.assistant(
                    tool_calls=(ToolCall("lookup", {"query": "tea"}, call_id="call-1"),)
                ),
                attributes={"turn": 1},
            )
            await memory.append_message(scope, Message.tool_result("lookup", "found tea"))
            history = await memory.history(scope)
            assert [entry.message.role for entry in history] == [Role.ASSISTANT, Role.TOOL]
            assert history[0].message.tool_calls[0].arguments["query"] == "tea"
            assert history[0].attributes["turn"] == 1

            user_scope = MemoryScope("user", "one")
            await memory.put_fact(user_scope, "drink", "tea")
            await memory.put_fact(user_scope, "drink", "coffee")
            current = await memory.get_fact(user_scope, "drink")
            assert current is not None and current.value == "coffee"
            await memory.forget_fact(user_scope, "drink")
            assert await memory.get_fact(user_scope, "drink") is None

            await memory.put_fact(user_scope, "drink", "tea")
            await memory.clear(scope)
            assert await memory.history(scope) == ()
            current = await memory.get_fact(user_scope, "drink")
            assert current is not None and current.value == "tea"
            await memory.clear(user_scope)
            assert await memory.get_fact(user_scope, "drink") is None
        finally:
            await database.aclose()

    asyncio.run(scenario())


def test_invalid_scope_and_input_are_refused() -> None:
    with pytest.raises(ValueError, match="scope key"):
        MemoryScope("conversation", "  ")

    async def scenario() -> None:
        database = await open_database(
            SqliteSettings(path=":memory:", journal_mode="MEMORY", synchronous="NORMAL")
        )
        try:
            memory = ConversationMemory(database)
            await memory.initialize()
            scope = MemoryScope("user", "one")
            with pytest.raises(ValueError, match="JSON serializable"):
                await memory.put_fact(scope, "bad", object())
            with pytest.raises(ValueError, match="255 characters"):
                await memory.put_fact(scope, "x" * 256, "value")
            with pytest.raises(ValueError, match="limit"):
                await memory.history(scope, limit=0)
        finally:
            await database.aclose()

    asyncio.run(scenario())
