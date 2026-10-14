"""The same configuration through a ``Plugin``, for an application that composes in sections.

A plugin is not required: :func:`~xyberos_observability.logs.configure_logging` is the explicit call
a composition root can make on its own. Declaring the settings as a plugin's ``config_type`` is the
other door to the same room, and it is the one an application that already composes in sections
wants — ``[plugins.observability]`` in ``xyberos.toml``, ``XYBEROS_PLUGINS__OBSERVABILITY__LEVEL`` in
the environment, or an explicit mapping, with the precedence every other plugin section has.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from xyberos.plugins.protocol import Plugin

from xyberos_observability.observability import Observability
from xyberos_observability.settings import ObservabilitySettings

if TYPE_CHECKING:
    from xyberos.app import App

__all__ = ["ObservabilityPlugin"]


class ObservabilityPlugin(Plugin[ObservabilitySettings]):
    """Configure one logging handler and provide :class:`Observability`, from a plugin section.

    .. code-block:: python

        app.add_plugin(ObservabilityPlugin())  # reads [plugins.observability]
        app.add_plugin(ObservabilityPlugin(), config={"level": "DEBUG", "service": "checkout"})

    The handler is installed while the plugin registers and removed when the application stops; the
    :class:`Observability` object is a provider, so a service that wants to open a span of its own
    asks for it by type instead of reaching for a module-level singleton.
    """

    name: ClassVar[str] = "observability"
    api_version: ClassVar[str] = "1"
    requires: ClassVar[tuple[str, ...]] = ()
    config_type: ClassVar[type[object] | None] = ObservabilitySettings

    def __init__(self) -> None:
        self._observability: Observability | None = None

    @property
    def observability(self) -> Observability | None:
        """The object this plugin built, once it has registered."""
        return self._observability

    def register(self, app: App, config: ObservabilitySettings) -> None:
        observability = Observability(config)
        observability.configure_logging()
        try:
            app.provide(Observability, instance=observability)
        except Exception:
            # A handler left behind by a registration that failed would be a leak the application
            # cannot even name, since it never received the object that owns it.
            observability.shutdown()
            raise
        self._observability = observability

    async def stop(self) -> None:
        """Remove the handler and shut the tracer provider down."""
        observability, self._observability = self._observability, None
        if observability is not None:
            observability.shutdown()
