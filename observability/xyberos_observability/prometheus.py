"""Prometheus exporter — counts Xyberos events per name (lazy ``prometheus_client``)."""

from __future__ import annotations

import importlib
from collections import defaultdict
from typing import Any

from xyberos.events import Event
from xyberos.exceptions.provider import ProviderError


class PrometheusExporter:
    """Increments a ``xyberos_events_total`` counter labeled by event name."""

    METRIC_NAME = "xyberos_events_total"

    def __init__(self, *, registry: Any | None = None) -> None:
        self._registry = registry
        self._counter: Any = None
        self._counts: dict[str, int] = defaultdict(int)

    def export(self, event: Event) -> None:
        self._counts[event.name] += 1
        self._get_counter().labels(event=event.name).inc()

    def __call__(self, event: Event) -> None:
        self.export(event)

    def value(self, event_name: str) -> float:
        """The current count for ``event_name`` (0.0 when never emitted)."""
        return float(self._counts.get(event_name, 0.0))

    # -- internals ----------------------------------------------------------

    def _get_counter(self) -> Any:
        if self._counter is not None:
            return self._counter
        try:
            prometheus_client = importlib.import_module("prometheus_client")
        except ImportError as exc:
            raise ProviderError(
                "Prometheus requires 'prometheus-client'; install with "
                "'pip install xyberos-observability[prometheus]'"
            ) from exc
        self._counter = prometheus_client.Counter(
            self.METRIC_NAME,
            "Xyberos events by name",
            ["event"],
            registry=self._registry,
        )
        return self._counter
