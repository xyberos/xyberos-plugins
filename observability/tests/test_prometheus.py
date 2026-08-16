"""Tests for the Prometheus exporter (isolated registry)."""

from __future__ import annotations

import importlib.util

import pytest
from xyberos.events import Event

from xyberos_observability import PrometheusExporter

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("prometheus_client") is None,
    reason="prometheus-client is not installed",
)


def test_counter_increments_per_event_name():
    from prometheus_client import CollectorRegistry

    registry = CollectorRegistry()
    exporter = PrometheusExporter(registry=registry)
    exporter.export(Event(name="brain.response_produced"))
    exporter.export(Event(name="brain.response_produced"))
    exporter.export(Event(name="memory.stored"))

    assert exporter.value("brain.response_produced") == 2.0
    assert exporter.value("memory.stored") == 1.0
    assert exporter.value("never.emitted") == 0.0


def test_value_without_injected_registry():
    # default (global) registry — value() must still reflect counts
    exporter = PrometheusExporter()
    exporter.export(Event(name="kernel.started"))
    exporter.export(Event(name="kernel.started"))
    assert exporter.value("kernel.started") == 2.0
