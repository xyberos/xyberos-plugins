"""Queue adapters: Redis Streams, RabbitMQ, Kafka (lazy drivers, injectable)."""

from __future__ import annotations

import importlib
import os
from typing import Any

from xyberos.exceptions.provider import ProviderError


def _require(package: str, extra: str) -> Any:
    try:
        return importlib.import_module(package)
    except ImportError as exc:
        raise ProviderError(
            f"the '{package}' package is required for {extra}; install with "
            f"'pip install xyberos-queues[{extra}]'"
        ) from exc


class RedisStreamsQueue:
    """Redis Streams (lazy ``redis``; injectable client for tests)."""

    name = "redis"

    def __init__(
        self,
        *,
        url: str | None = None,
        client: Any | None = None,
        stream_prefix: str = "xyberos:queue",
    ) -> None:
        self._url = url
        self._client = client
        self._prefix = stream_prefix

    def publish(self, topic: str, message: str) -> None:
        self._get_client().xadd(self._stream(topic), {"message": message})

    def poll(self, topic: str, timeout: float = 0.1) -> str | None:
        # XRANGE (oldest first) + XDEL drains the stream like a queue and works
        # on both real Redis and fakeredis (no XREAD-">" quirks).
        client = self._get_client()
        stream = self._stream(topic)
        entries = client.xrange(stream, count=1)
        if not entries:
            return None
        entry_id, fields = entries[0]
        client.xdel(stream, entry_id)
        value = fields.get(b"message", fields.get("message"))
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    def close(self) -> None:
        pass

    def _stream(self, topic: str) -> str:
        return f"{self._prefix}:{topic}"

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        redis = _require("redis", "redis")
        self._client = redis.from_url(self._url) if self._url else redis.Redis()
        return self._client


class RabbitMqQueue:
    """RabbitMQ via lazy ``pika`` (injectable channel for tests)."""

    name = "rabbitmq"

    def __init__(
        self,
        queue: str = "xyberos",
        *,
        host: str = "localhost",
        port: int = 5672,
        channel: Any | None = None,
    ) -> None:
        self._queue = queue
        self._host = host
        self._port = port
        self._channel = channel

    def _get_channel(self) -> Any:
        if self._channel is not None:
            return self._channel
        pika = _require("pika", "rabbitmq")
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=self._host, port=self._port)
        )
        channel = connection.channel()
        channel.queue_declare(queue=self._queue)
        self._channel = channel
        return channel

    def publish(self, topic: str, message: str) -> None:
        self._get_channel().basic_publish(exchange="", routing_key=self._queue, body=message)

    def poll(self, topic: str, timeout: float = 0.1) -> str | None:
        method, _properties, body = self._get_channel().basic_get(self._queue, auto_ack=True)
        if method is None or body is None:
            return None
        return body.decode("utf-8") if isinstance(body, bytes) else str(body)

    def close(self) -> None:
        pass


class KafkaQueue:
    """Apache Kafka via lazy ``kafka-python`` (injectable producer/consumer)."""

    name = "kafka"

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        *,
        producer: Any | None = None,
        consumer: Any | None = None,
        group_id: str = "xyberos",
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer = producer
        self._consumer = consumer
        self._group_id = group_id

    def publish(self, topic: str, message: str) -> None:
        producer = self._get_producer()
        producer.send(topic, value=message.encode("utf-8"))
        producer.flush()

    def poll(self, topic: str, timeout: float = 0.1) -> str | None:
        consumer = self._get_consumer(topic)
        records = consumer.poll(timeout_ms=int(timeout * 1000), max_records=1)
        for _tp, messages in records.items():
            for message in messages:
                return message.value.decode("utf-8")
        return None

    def close(self) -> None:
        if self._consumer is not None:
            try:
                self._consumer.close()
            except Exception:
                pass
            self._consumer = None
        if self._producer is not None:
            try:
                self._producer.close()
            except Exception:
                pass
            self._producer = None

    def _get_producer(self) -> Any:
        if self._producer is not None:
            return self._producer
        kafka = _require("kafka", "kafka")
        self._producer = kafka.KafkaProducer(bootstrap_servers=self._bootstrap_servers)
        return self._producer

    def _get_consumer(self, topic: str) -> Any:
        if self._consumer is not None:
            return self._consumer
        kafka = _require("kafka", "kafka")
        self._consumer = kafka.KafkaConsumer(
            topic, bootstrap_servers=self._bootstrap_servers, group_id=self._group_id
        )
        return self._consumer
