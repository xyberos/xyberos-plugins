"""OpenTelemetry exporter — one span per Xyberos event (lazy SDK).

Builds a default SDK ``TracerProvider`` with a ``SimpleSpanProcessor`` on an
``InMemorySpanExporter`` so traces are inspectable in tests; a ``tracer`` (or a
``span_exporter``) can be injected. Import ``opentelemetry-sdk`` lazily.
"""

from __future__ import annotations

import importlib
from typing import Any

from xyberos.events import Event
from xyberos.exceptions.provider import ProviderError


class OpenTelemetryExporter:
    """Turns each :class:`~xyberos.events.Event` into an OTel span."""

    def __init__(self, *, tracer: Any | None = None, span_exporter: Any | None = None) -> None:
        self._tracer = tracer
        self._span_exporter = span_exporter

    def export(self, event: Event) -> None:
        tracer = self._get_tracer()
        with tracer.start_as_current_span(event.name) as span:
            span.set_attribute("event.name", event.name)
            for key, value in (event.data or {}).items():
                span.set_attribute(f"event.{key}", str(value))
            prompt = getattr(event.context, "prompt", None)
            if prompt:
                span.set_attribute("event.prompt", str(prompt))

    def __call__(self, event: Event) -> None:
        self.export(event)

    def spans(self) -> list[Any]:
        """Return finished spans from the injected/exposed span exporter."""
        exporter = self._get_span_exporter()
        return list(exporter.get_finished_spans()) if exporter is not None else []

    # -- internals ----------------------------------------------------------

    def _get_tracer(self) -> Any:
        if self._tracer is not None:
            return self._tracer
        try:
            opentelemetry_trace = importlib.import_module("opentelemetry.trace")
            otel_sdk = importlib.import_module("opentelemetry.sdk.trace")
        except ImportError as exc:
            raise ProviderError(
                "OpenTelemetry requires 'opentelemetry-sdk'; install with "
                "'pip install xyberos-observability[otel]'"
            ) from exc
        provider = otel_sdk.TracerProvider()
        provider.add_span_processor(self._span_processor(self._get_span_exporter()))
        self._tracer = opentelemetry_trace.get_tracer("xyberos", tracer_provider=provider)
        return self._tracer

    def _get_span_exporter(self) -> Any:
        if self._span_exporter is not None:
            return self._span_exporter
        try:
            in_memory = importlib.import_module(
                "opentelemetry.sdk.trace.export.in_memory_span_exporter"
            )
        except ImportError as exc:  # pragma: no cover - guarded by _get_tracer
            raise ProviderError("OpenTelemetry SDK is not installed") from exc
        self._span_exporter = in_memory.InMemorySpanExporter()
        return self._span_exporter

    @staticmethod
    def _span_processor(exporter: Any) -> Any:
        export_module = importlib.import_module("opentelemetry.sdk.trace.export")
        return export_module.SimpleSpanProcessor(exporter)
