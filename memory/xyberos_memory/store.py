"""Database-backed conversation history and scoped facts."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    insert,
    select,
)

from xyberos.ai import Message, Role, ToolCall
from xyberos.database import DatabaseProvider
from xyberos_memory.models import ConversationEntry, MemoryFact, MemoryScope

_METADATA = MetaData()
_MESSAGES = Table(
    "xyberos_memory_messages",
    _METADATA,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("id", String(36), nullable=False, unique=True),
    Column("scope_namespace", String(255), nullable=False),
    Column("scope_key", String(1024), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("message", JSON, nullable=False),
    Column("attributes", JSON, nullable=False),
)
Index(
    "ix_xyberos_memory_messages_scope_time",
    _MESSAGES.c.scope_namespace,
    _MESSAGES.c.scope_key,
    _MESSAGES.c.sequence,
)
_FACTS = Table(
    "xyberos_memory_facts",
    _METADATA,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("id", String(36), nullable=False, unique=True),
    Column("scope_namespace", String(255), nullable=False),
    Column("scope_key", String(1024), nullable=False),
    Column("fact_key", String(255), nullable=False),
    Column("value", JSON, nullable=True),
    Column("deleted", Boolean, nullable=False),
    Column("created_at", String(40), nullable=False),
)
Index(
    "ix_xyberos_memory_facts_scope_key_time",
    _FACTS.c.scope_namespace,
    _FACTS.c.scope_key,
    _FACTS.c.fact_key,
    _FACTS.c.sequence,
)


class ConversationMemory:
    """Persist messages and explicitly scoped facts using an application's database provider.

    The application must call :meth:`initialize` before using this object. It owns the provider's
    lifecycle; this class only opens transactions for its own operations.
    """

    def __init__(self, database: DatabaseProvider) -> None:
        self._database = database

    async def initialize(self) -> None:
        """Create this package's tables if they do not already exist."""
        async with self._database.transaction() as connection:
            await connection.run_sync(_METADATA.create_all)

    async def append_message(
        self,
        scope: MemoryScope,
        message: Message,
        *,
        attributes: Mapping[str, object] | None = None,
    ) -> ConversationEntry:
        """Append one message without changing or interpreting its content."""
        message_data = _message_to_data(message)
        entry_attributes = {} if attributes is None else dict(attributes)
        _require_json_value(entry_attributes, "message attributes")
        created_at = _now()
        entry_id = str(uuid.uuid4())
        async with self._database.transaction() as connection:
            await connection.execute(
                insert(_MESSAGES).values(
                    id=entry_id,
                    scope_namespace=scope.namespace,
                    scope_key=scope.key,
                    created_at=created_at.isoformat(),
                    message=message_data,
                    attributes=entry_attributes,
                )
            )
        return ConversationEntry(entry_id, scope, message, entry_attributes, created_at)

    async def history(
        self, scope: MemoryScope, *, limit: int = 100
    ) -> tuple[ConversationEntry, ...]:
        """Return the latest messages in chronological order."""
        if not 1 <= limit <= 1000:
            raise ValueError("history limit must be between 1 and 1000")
        statement = (
            select(_MESSAGES)
            .where(
                _MESSAGES.c.scope_namespace == scope.namespace,
                _MESSAGES.c.scope_key == scope.key,
            )
            .order_by(_MESSAGES.c.sequence.desc())
            .limit(limit)
        )
        async with self._database.transaction() as connection:
            result = await connection.execute(statement)
            rows = list(result.mappings())
        entries = [
            ConversationEntry(
                id=row["id"],
                scope=scope,
                message=_message_from_data(row["message"]),
                attributes=row["attributes"],
                created_at=_parse_datetime(row["created_at"]),
            )
            for row in reversed(rows)
        ]
        return tuple(entries)

    async def put_fact(self, scope: MemoryScope, key: str, value: object) -> MemoryFact:
        """Append a fact value; repeated keys replace the value returned by :meth:`get_fact`."""
        fact_key = _validate_fact_key(key)
        _require_json_value(value, "fact value")
        created_at = _now()
        async with self._database.transaction() as connection:
            await connection.execute(
                insert(_FACTS).values(
                    id=str(uuid.uuid4()),
                    scope_namespace=scope.namespace,
                    scope_key=scope.key,
                    fact_key=fact_key,
                    value=value,
                    deleted=False,
                    created_at=created_at.isoformat(),
                )
            )
        return MemoryFact(scope, fact_key, value, created_at)

    async def get_fact(self, scope: MemoryScope, key: str) -> MemoryFact | None:
        """Return the latest non-forgotten value for a fact key."""
        fact_key = _validate_fact_key(key)
        statement = (
            select(_FACTS)
            .where(
                _FACTS.c.scope_namespace == scope.namespace,
                _FACTS.c.scope_key == scope.key,
                _FACTS.c.fact_key == fact_key,
            )
            .order_by(_FACTS.c.sequence.desc())
            .limit(1)
        )
        async with self._database.transaction() as connection:
            row = (await connection.execute(statement)).mappings().first()
        if row is None or row["deleted"]:
            return None
        return MemoryFact(scope, fact_key, row["value"], _parse_datetime(row["created_at"]))

    async def forget_fact(self, scope: MemoryScope, key: str) -> None:
        """Append a tombstone so an older value cannot reappear."""
        fact_key = _validate_fact_key(key)
        created_at = _now()
        async with self._database.transaction() as connection:
            await connection.execute(
                insert(_FACTS).values(
                    id=str(uuid.uuid4()),
                    scope_namespace=scope.namespace,
                    scope_key=scope.key,
                    fact_key=fact_key,
                    value=None,
                    deleted=True,
                    created_at=created_at.isoformat(),
                )
            )

    async def clear(self, scope: MemoryScope) -> None:
        """Delete all messages and fact history in a scope."""
        async with self._database.transaction() as connection:
            await connection.execute(
                delete(_MESSAGES).where(
                    _MESSAGES.c.scope_namespace == scope.namespace,
                    _MESSAGES.c.scope_key == scope.key,
                )
            )
            await connection.execute(
                delete(_FACTS).where(
                    _FACTS.c.scope_namespace == scope.namespace,
                    _FACTS.c.scope_key == scope.key,
                )
            )


def _message_to_data(message: object) -> dict[str, object]:
    if not isinstance(message, Message):
        raise TypeError(f"message must be a xyberos.ai.Message, got {type(message).__name__}")
    return {
        "role": message.role.value,
        "content": message.content,
        "tool_calls": [
            {"name": call.name, "arguments": dict(call.arguments), "call_id": call.call_id}
            for call in message.tool_calls
        ],
        "tool_name": message.tool_name,
    }


def _message_from_data(value: object) -> Message:
    data = _json_object(value, "stored message")
    role = data.get("role")
    content = data.get("content")
    tool_name = data.get("tool_name")
    raw_tool_calls = data.get("tool_calls")
    if not isinstance(role, str):
        raise ValueError("stored message role is not a string")
    if not isinstance(content, str):
        raise ValueError("stored message content is not a string")
    if tool_name is not None and not isinstance(tool_name, str):
        raise ValueError("stored message tool_name is not a string or null")
    if not isinstance(raw_tool_calls, list):
        raise ValueError("stored message tool_calls is not a JSON array")
    tool_calls: list[ToolCall] = []
    for raw_call in cast(list[object], raw_tool_calls):
        call_data = _json_object(raw_call, "stored message tool call")
        name = call_data.get("name")
        arguments = call_data.get("arguments")
        call_id = call_data.get("call_id")
        if not isinstance(name, str) or not isinstance(call_id, str):
            raise ValueError("stored message tool call name and call_id must be strings")
        parsed_arguments = _json_object(arguments, "stored message tool call arguments")
        tool_calls.append(
            ToolCall(
                name=name,
                arguments=parsed_arguments,
                call_id=call_id,
            )
        )
    return Message(
        role=Role(role),
        content=content,
        tool_calls=tuple(tool_calls),
        tool_name=tool_name,
    )


def _json_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    object_value = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in object_value):
        raise ValueError(f"{label} has a non-string key")
    return cast(dict[str, object], value)


def _validate_fact_key(key: object) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ValueError("fact key must be a non-empty string")
    normalized = key.strip()
    if len(normalized) > 255:
        raise ValueError("fact key must be at most 255 characters")
    return normalized


def _require_json_value(value: object, label: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be JSON serializable") from error


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"stored timestamp has no timezone: {value!r}")
    return parsed.astimezone(timezone.utc)
