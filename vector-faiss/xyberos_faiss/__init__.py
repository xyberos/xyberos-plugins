"""FAISS VectorStore plugin (RFC-0019, M4)."""

from .plugin import FaissPlugin
from .vector import FaissVectorStore

__all__ = ["FaissPlugin", "FaissVectorStore"]
