"""The one call: a handler, a level, a format, and the runtime's own context filter.

The runtime never installs a handler, sets a level, or picks a format, because a library that
configures logging fights the application that embeds it. This module is the other half of that
promise: the application asks for a sink, explicitly, once, and gets back the handle that takes it
away. Nothing here runs on its own, and nothing here patches the logging module.

What is installed is deliberately small — one ``StreamHandler``, one level, one format, and
:class:`~xyberos.runtime.context.ContextLogFilter`, which copies the current diagnostic context onto
every record so the correlation id a request is already logged under also reaches the sink.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import IO

from xyberos.runtime.context import ContextLogFilter

from xyberos_observability.settings import ObservabilitySettings

__all__ = ["LoggingSetup", "configure_logging"]


@dataclass
class LoggingSetup:
    """What :func:`configure_logging` installed, and the one call that removes it."""

    logger: logging.Logger
    """The logger the handler was attached to."""

    handler: logging.Handler
    """The handler, so an application can swap its stream or its formatter if it wants to."""

    level: int
    """The level this call set the logger to."""

    previous_level: int
    """The level the logger had before, which :meth:`shutdown` gives back."""

    _closed: bool = field(default=False, repr=False)

    def shutdown(self) -> None:
        """Detach the handler and restore the level. Calling it twice does nothing the second time.

        The stream is left open: an application that passed one owns it, and a handler that closed
        a buffer the application still writes to would be a surprising thing for a log sink to do.
        The level is restored only while it is still the one this call set — a deployment that
        changed it afterwards meant that, and this package does not overrule it.
        """
        if self._closed:
            return
        self._closed = True
        self.logger.removeHandler(self.handler)
        self.handler.close()
        if self.logger.level == self.level:
            self.logger.setLevel(self.previous_level)


def configure_logging(
    settings: ObservabilitySettings | None = None, *, stream: IO[str] | None = None
) -> LoggingSetup:
    """Install the handler, the level, the format, and ``ContextLogFilter``, and return the handle.

    ``stream`` defaults to what ``logging.StreamHandler`` uses, which is standard error. The level is
    set on the logger rather than on the handler, so a deployment filters once, in the place its
    records are created, and nothing is configured for a namespace the caller did not name.
    """
    active = ObservabilitySettings() if settings is None else settings
    logger = logging.getLogger(active.logger) if active.logger else logging.getLogger()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(active.format))
    handler.addFilter(ContextLogFilter())
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(active.level_number)
    return LoggingSetup(
        logger=logger,
        handler=handler,
        level=active.level_number,
        previous_level=previous_level,
    )
