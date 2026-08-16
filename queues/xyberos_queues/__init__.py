"""Message queue plugin (RFC-0019, M9)."""

from .adapters import KafkaQueue, RabbitMqQueue, RedisStreamsQueue
from .contract import MessageQueue
from .plugin import QueuesPlugin

__all__ = ["KafkaQueue", "MessageQueue", "QueuesPlugin", "RabbitMqQueue", "RedisStreamsQueue"]
