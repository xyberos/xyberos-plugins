"""What this package is configured with, and the values it refuses.

The settings are a frozen dataclass rather than a mapping, so a misspelled setting fails where it is
written instead of becoming a key nothing reads — and so a ``Plugin`` can declare this type as its
``config_type``, which is how ``[plugins.observability]`` and ``XYBEROS_PLUGINS__OBSERVABILITY__LEVEL``
reach it with the precedence every other plugin section gets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from xyberos.errors import ConfigurationError
from xyberos.runtime.context import ContextLogFilter

__all__ = ["DEFAULT_FORMAT", "ObservabilitySettings"]

DEFAULT_FORMAT = "%(levelname)s %(name)s %(message)s %(xyberos_context)s"
"""The default format, which ends in the context the runtime's own filter attaches.

The observability page this package implements prints records verbatim as
``INFO orders.api looked up order 7 {'correlation_id': 'req-1'}``, and that trailing mapping is
``ContextLogFilter`` copying the current diagnostic context onto the record. A format that names
``%(xyberos_context)s`` renders it; a format that names something no record has is refused here
rather than raising in a handler on the first line a process tries to log.
"""


@dataclass(frozen=True)
class ObservabilitySettings:
    """Explicit settings for one application's logging and spans."""

    service: str = "xyberos"
    """The deployment's name, reported as the spans' ``service.name`` resource attribute."""

    level: str = "INFO"
    """The level the configured logger is set to, as a ``logging`` level name or its number."""

    format: str = DEFAULT_FORMAT
    """The handler's format. ``%(xyberos_context)s`` is the diagnostic context, not a payload."""

    logger: str = ""
    """The logger to configure: ``""`` is the root logger, which is the one that catches both the
    application's records and the framework's."""

    def __post_init__(self) -> None:
        if not self.service.strip():
            raise ConfigurationError("service must name the deployment, for example 'checkout'")
        _level_number(self.level)
        _probe_format(self.format)
        if self.logger != self.logger.strip():
            raise ConfigurationError("logger must not have surrounding whitespace")
        if self.logger and not all(part.isidentifier() for part in self.logger.split(".")):
            raise ConfigurationError(
                f"logger {self.logger!r} must be a dotted identifier such as 'xyberos.ai'"
            )

    @property
    def level_number(self) -> int:
        """The numeric level ``level`` names."""
        return _level_number(self.level)


def _level_number(level: str) -> int:
    if level.isdigit():
        return int(level)
    resolved = getattr(logging, level.upper(), None)
    if isinstance(resolved, bool) or not isinstance(resolved, int):
        raise ConfigurationError(
            f"level {level!r} is not a logging level; name one such as INFO or DEBUG, or its number"
        )
    return resolved


def _probe_format(template: str) -> None:
    """Refuse a format that could not be rendered against a record this package's handler writes."""
    if not template:
        raise ConfigurationError("format must not be empty")
    probe = logging.LogRecord(
        name="xyberos_observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="probe",
        args=(),
        exc_info=None,
    )
    ContextLogFilter().filter(probe)
    try:
        logging.Formatter(template).format(probe)
    except (KeyError, ValueError) as error:
        raise ConfigurationError(
            f"format {template!r} cannot be rendered against a log record: {error}"
        ) from error
