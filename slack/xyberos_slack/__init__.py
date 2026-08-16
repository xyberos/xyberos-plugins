"""Slack Web API plugin (RFC-0019, M7)."""

from .client import SlackClient
from .plugin import SlackPlugin

__all__ = ["SlackClient", "SlackPlugin"]
