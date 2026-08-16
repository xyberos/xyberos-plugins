"""Observability plugin entry point (RFC-0019, M10).

Wires an :class:`~xyberos.events.EventRecorder` (with the configured exporters)
into the app's ``EventBus``. Exporters are selected by name
(``OBSERVABILITY_EXPORTERS`` = comma-separated ``otel``, ``prometheus``,
``langfuse``, ``sentry``) or passed explicitly. With none configured the
plugin registers nothing (logs a warning).
"""

from __future__ import annotations

import os
from typing import Any

from xyberos.contracts import Plugin
from xyberos.events import EventRecorder, Exporter

from .langfuse import LangfuseExporter
from .otel import OpenTelemetryExporter
from .prometheus import PrometheusExporter
from .sentry import SentryExporter

EXPORTER_BUILDERS: dict[str, Any] = {
    "otel": lambda: OpenTelemetryExporter(),
    "prometheus": lambda: PrometheusExporter(),
    "langfuse": lambda: LangfuseExporter(),
    "sentry": lambda: SentryExporter(),
}


class ObservabilityPlugin(Plugin):
    """Subscribes an ``EventRecorder`` with the configured exporters."""

    def __init__(
        self,
        exporters: list[Exporter] | None = None,
        *,
        env_prefix: str = "OBSERVABILITY",
    ) -> None:
        self._exporters_arg = exporters
        self._env_prefix = env_prefix
        self._recorder: EventRecorder | None = None

    @property
    def name(self) -> str:
        return "observability"

    def exporters(self) -> list[Exporter]:
        if self._exporters_arg is not None:
            return list(self._exporters_arg)
        names = [
            name.strip().lower()
            for name in os.getenv(f"{self._env_prefix}_EXPORTERS", "").split(",")
            if name.strip()
        ]
        built: list[Exporter] = []
        for name in names:
            if name not in EXPORTER_BUILDERS:
                raise ValueError(
                    f"unknown exporter '{name}' (choose from {sorted(EXPORTER_BUILDERS)})"
                )
            built.append(EXPORTER_BUILDERS[name]())
        return built

    def register(self, kernel: object) -> None:
        try:
            exporters = self.exporters()
        except ValueError as exc:
            logger = getattr(kernel, "logger", None)
            if logger is not None and callable(getattr(logger, "warning", None)):
                logger.warning("observability plugin not configured: %s", exc)
            return
        if not exporters:
            logger = getattr(kernel, "logger", None)
            if logger is not None and callable(getattr(logger, "warning", None)):
                logger.warning(
                    "observability plugin not configured: set %s_EXPORTERS", self._env_prefix
                )
            return
        events = kernel.resolve("events")
        self._recorder = EventRecorder(exporters=exporters).subscribe_to(events)
        kernel.register("observability", self._recorder, replace=True)

    def unregister(self, kernel: object) -> None:
        if self._recorder is not None:
            self._recorder.unsubscribe_from(kernel.resolve("events"))
            self._recorder = None


#: Auto-discovered by ``app.load_entry_points()``.
plugin = ObservabilityPlugin()
