"""Queues plugin entry point (RFC-0019, M9)."""

from __future__ import annotations

import os
from typing import Any, cast

from xyberos.contracts import Plugin, Tool
from xyberos.tools import FunctionTool

from .adapters import KafkaQueue, RabbitMqQueue, RedisStreamsQueue
from .contract import MessageQueue


def _pop_tool(registry: Any, name: str) -> None:
    unregister = getattr(registry, "unregister", None)
    if callable(unregister):
        unregister(name)
        return
    store = getattr(registry, "_tools", None)
    if isinstance(store, dict):
        cast(dict[str, Any], store).pop(name, None)


class QueuesPlugin(Plugin):
    """Registers ``queue_publish`` / ``queue_poll`` for a configured provider."""

    def __init__(
        self,
        provider: str | None = None,
        *,
        env_prefix: str = "QUEUE",
        client: Any | None = None,
        channel: Any | None = None,
        producer: Any | None = None,
        consumer: Any | None = None,
    ) -> None:
        self._provider = (provider or os.getenv(f"{env_prefix}_PROVIDER") or "redis").lower()
        self._client = client
        self._channel = channel
        self._producer = producer
        self._consumer = consumer

    @property
    def name(self) -> str:
        return "queues"

    def message_queue(self) -> MessageQueue:
        name = self._provider
        if name == "redis":
            return RedisStreamsQueue(client=self._client)
        if name == "rabbitmq":
            return RabbitMqQueue(channel=self._channel)
        if name == "kafka":
            return KafkaQueue(producer=self._producer, consumer=self._consumer)
        raise ValueError(f"unknown queue provider '{name}' (redis | rabbitmq | kafka)")

    def tools(self) -> list[Tool]:
        queue = self.message_queue()

        def _publish(topic: str, message: str) -> dict[str, Any]:
            queue.publish(topic, message)
            return {"topic": topic, "published": True}

        def _poll(topic: str, timeout: float = 0.1) -> str | None:
            return queue.poll(topic, timeout)

        return [
            FunctionTool("queue_publish", _publish, description=f"Publish a message via {self._provider}."),
            FunctionTool("queue_poll", _poll, description=f"Poll one message from a {self._provider} topic."),
        ]

    def register(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            registry.register(tool)

    def unregister(self, kernel: object) -> None:
        registry = kernel.resolve("tools")
        for tool in self.tools():
            _pop_tool(registry, tool.name)


#: Auto-discovered by ``app.load_entry_points()``.
plugin = QueuesPlugin()
