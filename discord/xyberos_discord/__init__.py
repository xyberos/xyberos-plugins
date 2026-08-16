"""Discord bot API plugin (RFC-0019, M7)."""

from .client import DiscordClient
from .plugin import DiscordPlugin

__all__ = ["DiscordClient", "DiscordPlugin"]
