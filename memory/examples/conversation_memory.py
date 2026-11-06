"""Persist a conversation and a user-scoped fact in a local SQLite database."""

import asyncio

from xyberos_memory import ConversationMemory, MemoryScope

from xyberos.ai import Message
from xyberos.database import SqliteSettings, open_database


async def main() -> None:
    database = await open_database(SqliteSettings(path="var/memory.db"))
    try:
        memory = ConversationMemory(database)
        await memory.initialize()
        conversation = MemoryScope("conversation", "demo")
        await memory.append_message(conversation, Message.user("Remember that I like tea."))
        await memory.put_fact(MemoryScope("user", "demo-user"), "favorite_drink", "tea")
        for entry in await memory.history(conversation):
            print(entry.message.role.value, entry.message.content)
    finally:
        await database.aclose()


if __name__ == "__main__":
    asyncio.run(main())
