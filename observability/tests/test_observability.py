"""The object that owns the provider: what it refuses, what it drops, and what it releases."""

from __future__ import annotations

from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from xyberos.errors import ConfigurationError

from xyberos_observability import EventSpans, Observability, ObservabilitySettings


def test_an_exporter_beside_a_tracer_provider_is_refused() -> None:
    """A dropped telemetry sink is worse than a refusal, so the ambiguity is named."""
    with pytest.raises(ConfigurationError, match="not both"):
        Observability(
            ObservabilitySettings(),
            exporter=InMemorySpanExporter(),
            tracer_provider=TracerProvider(),
        )


def test_without_an_exporter_the_spans_are_created_and_dropped() -> None:
    """Nothing opens a socket the application did not ask for, and a span is still a span."""
    observability = Observability(ObservabilitySettings(service="checkout"))

    observability.tracer.start_span("workflow demo").end()
    sink = observability.event_sink()
    observability.shutdown()

    assert isinstance(sink, EventSpans)


def test_the_provider_is_shut_down_once_even_when_shutdown_is_called_twice() -> None:
    exporter = InMemorySpanExporter()
    observability = Observability(ObservabilitySettings(), exporter=exporter)

    observability.tracer.start_span("workflow demo").end()
    observability.shutdown()
    observability.shutdown()

    assert [span.name for span in exporter.get_finished_spans()] == ["workflow demo"]


def test_the_package_ships_its_types() -> None:
    marker = Path(__file__).resolve().parents[1] / "xyberos_observability" / "py.typed"

    assert marker.is_file(), "strict-mode consumers need the PEP 561 marker"
