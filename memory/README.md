# xyberos-memory

Persistent conversation history and explicitly scoped facts for Xyberos 2.x applications. The
package uses the application's public `DatabaseProvider`; it does not select or own a database
backend.

## Install

```powershell
python -m pip install "xyberos-memory"
```

The install includes Xyberos' `database` extra. Select and start a database provider in the
application, then give that provider to `ConversationMemory`.

## Use

```python
from xyberos.database import SqliteSettings, open_database
from xyberos.ai import Message
from xyberos_memory import ConversationMemory, MemoryScope


async def main() -> None:
    database = await open_database(SqliteSettings(path="var/app.db"))
    try:
        memory = ConversationMemory(database)
        await memory.initialize()

        conversation = MemoryScope("conversation", "conversation-123")
        await memory.append_message(conversation, Message.user("I prefer tea."))

        user = MemoryScope("user", "user-456")
        await memory.put_fact(user, "preferred_drink", "tea")
        fact = await memory.get_fact(user, "preferred_drink")
        print(fact.value if fact is not None else "unknown")
    finally:
        await database.aclose()
```

`history(scope, limit=100)` returns the latest Xyberos AI messages in chronological order, including
tool calls. `put_fact` appends a value; `get_fact` returns its latest value; and `forget_fact` records
a tombstone so an older value does not reappear. `clear(scope)` removes both messages and fact history
for that scope.

## Scope and security

`MemoryScope(namespace, key)` is a data partition, **not an authorization mechanism**. Derive scopes
from authenticated application state, never directly from untrusted request fields. The application
owns database startup, shutdown, migrations/backups, and authorization. The memory tables are created
by the explicit `initialize()` call.

## Development

```powershell
python -m pip install -e ".[test]"
python -m pytest
```
