"""Tests for the OpenTelemetry exporter (in-memory spans, no collector)."""

from __future__ import annotations

import importlib.util
from types import SimpleNamespace

import pytest
from xyberos.events import Event

from xyberos_observability import OpenTelemetryExporter

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("opentelemetry") is None,
    reason="opentelemetry-sdk is not installed",
)


def test_events_become_spans():
    exporter = OpenTelemetryExporter()
    exporter.export(Event(name="runtime.request_started", context=SimpleNamespace(prompt="hi"), data={"x": 1}))
    exporter.export(Event(name="brain.response_produced", data={"response": "hello"}))

    spans = exporter.spans()
    assert [span.name for span in spans] == ["runtime.request_started", "brain.response_produced"]
    assert spans[0].attributes["event.prompt"] == "hi"
    assert spans[1].attributes["event.response"] == "hello"


def test_exporter_is_callable():
    exporter = OpenTelemetryExporter()
    exporter(Event(name="kernel.started"))
    assert [span.name for span in exporter.spans()] == ["kernel.started"]
