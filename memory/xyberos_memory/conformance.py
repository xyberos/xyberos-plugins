"""Run the memory behavior checks against the core SQLite provider."""

from __future__ import annotations

import asyncio

from xyberos.ai import Message
from xyberos.database import SqliteSettings, open_database
from xyberos_memory import ConversationMemory, MemoryScope


async def assert_memory_contract(memory: ConversationMemory) -> tuple[str, ...]:
    """Check message round-tripping, scope isolation, fact replacement, and forgetting."""
    await memory.initialize()
    first = MemoryScope("conformance", "first")
    other = MemoryScope("conformance", "other")
    await memory.append_message(first, Message.user("first"))
    await memory.append_message(other, Message.user("other"))
    if tuple(item.message.content for item in await memory.history(first)) != ("first",):
        raise AssertionError("history must isolate one scope from another")
    checked = ["message history is isolated by scope"]

    await memory.put_fact(first, "favorite", "tea")
    await memory.put_fact(first, "favorite", "coffee")
    fact = await memory.get_fact(first, "favorite")
    if fact is None or fact.value != "coffee":
        raise AssertionError("get_fact must return the latest value")
    checked.append("fact lookup returns the latest value")

    await memory.forget_fact(first, "favorite")
    if await memory.get_fact(first, "favorite") is not None:
        raise AssertionError("a forgotten fact must not expose an older value")
    checked.append("forget_fact hides prior values")

    await memory.clear(first)
    if await memory.history(first):
        raise AssertionError("clear must remove scoped messages")
    if tuple(item.message.content for item in await memory.history(other)) != ("other",):
        raise AssertionError("clear must not remove another scope")
    checked.append("clear is scoped")
    return tuple(checked)


def main() -> int:
    """Run the contract against an isolated in-memory SQLite database."""

    async def run() -> tuple[str, ...]:
        database = await open_database(
            SqliteSettings(path=":memory:", journal_mode="MEMORY", synchronous="NORMAL")
        )
        try:
            return await assert_memory_contract(ConversationMemory(database))
        finally:
            await database.aclose()

    for check in asyncio.run(run()):
        print(f"ok: {check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
