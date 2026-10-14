"""Explicit settings for a page renderer, refused where a value would fail later.

A template directory and a static mount path are the two things a page-serving setup must decide,
and both fail late: a missing directory is a ``TemplateNotFound`` on the first request that needs
it, and a mount path without a leading slash is served at a path nobody linked to. They are checked
here, at construction, so the failure names the setting instead of the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xyberos.errors import ConfigurationError


def _require_bool(value: object, name: str) -> None:
    """A field typed ``bool`` is not enough: settings are often built from untyped configuration.

    ``autoescape="yes"`` and ``enable_async=1`` would both be accepted and quietly mean something
    other than a switch, so they are refused by name instead.
    """
    if not isinstance(value, bool):
        raise ConfigurationError(f"{name} must be a bool")


@dataclass(frozen=True)
class TemplatesSettings:
    """Where pages come from, and the two rendering decisions this package owns.

    ``autoescape`` is a plain switch rather than an extension list, because an extension list is how
    a template named ``page.j2`` ends up unescaped. ``enable_async`` chooses between the two
    off-loop strategies described on :meth:`~xyberos_templates.contract.Templates.render`; it is not
    an on/off switch for rendering.
    """

    directory: str | Path
    autoescape: bool = True
    enable_async: bool = False
    static_path: str = "/static"

    def __post_init__(self) -> None:
        directory = self.directory
        if isinstance(directory, str) and not directory.strip():
            raise ConfigurationError("directory must not be empty")
        path = Path(directory)
        if not path.exists():
            raise ConfigurationError(f"template directory {str(path)!r} does not exist")
        if not path.is_dir():
            raise ConfigurationError(f"template directory {str(path)!r} is not a directory")
        _require_bool(self.autoescape, "autoescape")
        _require_bool(self.enable_async, "enable_async")
        if not self.static_path:
            raise ConfigurationError("static_path must not be empty")
        if not self.static_path.startswith("/"):
            raise ConfigurationError(f"static_path {self.static_path!r} must start with '/'")
        if self.static_path == "/":
            raise ConfigurationError("static_path must not be the site root")

    @property
    def templates_directory(self) -> Path:
        """The template directory as a path, so callers do not repeat the conversion."""
        return Path(self.directory)
