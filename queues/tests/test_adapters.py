"""Tests for the queue adapters (fakeredis / fake clients, no servers)."""

from __future__ import annotations

import pytest

from xyberos_queues import KafkaQueue, RabbitMqQueue, RedisStreamsQueue


@pytest.fixture()
def redis_client():
    return pytest.importorskip("fakeredis").FakeStrictRedis()


def test_redis_streams_roundtrip(redis_client):
    queue = RedisStreamsQueue(client=redis_client)
    queue.publish("events", "hello")
    assert queue.poll("events") == "hello"
    assert queue.poll("events", timeout=0.01) is None  # drained


class _FakePikaChannel:
    def __init__(self):
        self.messages: list[str] = []

    def queue_declare(self, **kwargs):
        return None

    def basic_publish(self, **kwargs):
        self.messages.append(kwargs["body"])

    def basic_get(self, queue, auto_ack):
        if self.messages:
            return ("method", None, self.messages.pop(0))
        return (None, None, None)


def test_rabbitmq_roundtrip():
    channel = _FakePikaChannel()
    queue = RabbitMqQueue(channel=channel)
    queue.publish("q", "hello")
    assert queue.poll("q") == "hello"
    assert queue.poll("q") is None


class _FakeKafkaProducer:
    def __init__(self):
        self.sent: list[bytes] = []

    def send(self, topic, value):
        self.sent.append(value)
        return None

    def flush(self):
        pass

    def close(self):
        pass


class _FakeKafkaConsumer:
    def __init__(self, messages: list[bytes]):
        self._messages = messages
        self.closed = False

    def poll(self, **kwargs):
        if self._messages:
            return {"tp": [type("M", (), {"value": self._messages.pop(0)})()]}
        return {}

    def close(self):
        self.closed = True


def test_kafka_roundtrip():
    producer = _FakeKafkaProducer()
    consumer = _FakeKafkaConsumer([b"hello"])
    queue = KafkaQueue(producer=producer, consumer=consumer)
    queue.publish("topic", "world")
    assert producer.sent == [b"world"]
    assert queue.poll("topic") == "hello"
    queue.close()
    assert consumer.closed
