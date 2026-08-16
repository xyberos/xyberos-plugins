"""GitLab REST plugin (RFC-0019, M7)."""

from .client import GitlabClient
from .plugin import GitlabPlugin

__all__ = ["GitlabClient", "GitlabPlugin"]
