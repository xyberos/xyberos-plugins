"""Redis plugin (RFC-0019, M4): vector store + memory + cache backing.

* :class:`RedisVectorStore` — a :class:`~xyberos.contracts.VectorStore` backed
  by Redis hashes (can also back :class:`~xyberos.router.CacheResponder`).
* :class:`RedisMemory` — a :class:`~xyberos.contracts.Memory` backed by a Redis
  list.
* :class:`RedisStringCache` — a small exact-match string cache for ephemeral
  state.

``redis`` is imported lazily on first use and a clear ``ProviderError`` is
raised when it is missing (``pip install xyberos[state]``).
"""

from .cache import RedisStringCache
from .memory import RedisMemory
from .plugin import RedisPlugin
from .vector import RedisVectorStore

__all__ = ["RedisMemory", "RedisPlugin", "RedisStringCache", "RedisVectorStore"]
