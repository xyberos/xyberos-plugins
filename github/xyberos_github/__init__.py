"""GitHub REST plugin (RFC-0019, M7)."""

from .client import GithubClient
from .plugin import GithubPlugin

__all__ = ["GithubClient", "GithubPlugin"]
