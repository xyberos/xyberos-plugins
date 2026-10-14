"""The spans: a run's events, the naming contract, and the status each ending gets.

Everything runs against the in-memory span exporter, so a test reads exactly what a collector would
have received, with no network and no collector.
"""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from xyberos import (
    EventType,
    Workflow,
    WorkflowEvent,
    WorkflowExecutionError,
    bind_correlation_id,
)

from xyberos_observability import EventSpans, Observability, ObservabilitySettings


def observed(exporter: InMemorySpanExporter) -> Observability:
    return Observability(ObservabilitySettings(service="checkout"), exporter=exporter)


def names(spans: tuple[ReadableSpan, ...]) -> list[str]:
    return [span.name for span in spans]


def only(spans: tuple[ReadableSpan, ...], name: str) -> ReadableSpan:
    """Return the one span with this name, so an assertion says which span it is about."""
    matching = [span for span in spans if span.name == name]
    assert len(matching) == 1, f"expected one span named {name!r}, got {names(spans)}"
    return matching[0]


def event(
    event_type: EventType,
    sequence: int,
    *,
    step: str | None = None,
    attempt: int | None = None,
    duration: float | None = None,
    detail: str | None = None,
    error_type: str | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        type=event_type,
        sequence=sequence,
        workflow="demo",
        version="1",
        timestamp=0.0,
        step=step,
        attempt=attempt,
        duration=duration,
        detail=detail,
        error_type=error_type,
        correlation_id="corr-run",
    )


def test_a_run_becomes_a_workflow_span_with_a_child_span_per_step() -> None:
    exporter = InMemorySpanExporter()
    observability = observed(exporter)

    async def scenario() -> None:
        async def first(value: object, context: object) -> object:
            return value

        async def second(value: object, context: object) -> object:
            return value

        workflow = (
            Workflow("demo")
            .step("first", first)
            .step("second", second)
            .edge("first", "second")
        )
        with bind_correlation_id("corr-run"):
            await workflow.run(input="x", on_event=observability.event_sink())

    asyncio.run(scenario())
    observability.shutdown()

    spans = exporter.get_finished_spans()
    assert sorted(names(spans)) == ["step demo.first", "step demo.second", "workflow demo"]

    run = only(spans, "workflow demo")
    assert run.attributes["xyberos.workflow"] == "demo"
    assert run.attributes["xyberos.workflow.version"] == "1"
    assert run.attributes["xyberos.event.type"] == "workflow_succeeded"
    assert run.attributes["xyberos.correlation_id"] == "corr-run"
    assert run.status.status_code is StatusCode.OK

    step = only(spans, "step demo.first")
    assert step.attributes["xyberos.step"] == "first"
    assert step.attributes["xyberos.attempt"] == 1
    assert step.attributes["xyberos.event.type"] == "step_succeeded"
    assert isinstance(step.attributes["xyberos.duration"], float)
    assert step.status.status_code is StatusCode.OK
    assert step.parent is not None, "a step span belongs to the run that emitted it"
    assert step.parent.span_id == run.context.span_id


def test_a_step_no_branch_reached_is_still_a_span() -> None:
    exporter = InMemorySpanExporter()
    observability = observed(exporter)

    async def scenario() -> None:
        async def classify(value: object, context: object) -> object:
            return value

        async def never(value: object, context: object) -> object:
            return "never"

        workflow = (
            Workflow("demo")
            .step("classify", classify)
            .step("never", never)
            .edge("classify", "never", when=lambda value: False)
        )
        await workflow.run(input=None, on_event=observability.event_sink())

    asyncio.run(scenario())
    observability.shutdown()

    skipped = only(exporter.get_finished_spans(), "step demo.never")
    assert skipped.attributes["xyberos.event.type"] == "step_skipped"
    assert skipped.attributes["xyberos.event.detail"] == "no branch reached this step"
    assert skipped.status.status_code is StatusCode.OK


def test_a_failed_run_marks_the_step_and_the_run_as_errors() -> None:
    exporter = InMemorySpanExporter()
    observability = observed(exporter)

    async def scenario() -> None:
        async def only_step(value: object, context: object) -> object:
            raise ValueError("the payload was not what the step promised")

        with pytest.raises(WorkflowExecutionError):
            await Workflow("demo").step("only", only_step).run(
                input=None, on_event=observability.event_sink()
            )

    asyncio.run(scenario())
    observability.shutdown()

    spans = exporter.get_finished_spans()
    step = only(spans, "step demo.only")
    assert step.status.status_code is StatusCode.ERROR
    assert step.attributes["xyberos.error_type"] == "ValueError"
    assert step.attributes["xyberos.event.type"] == "step_failed"

    run = only(spans, "workflow demo")
    assert run.status.status_code is StatusCode.ERROR
    assert run.attributes["xyberos.event.type"] == "workflow_failed"


def test_a_retry_is_an_event_on_the_run_and_a_second_span_for_the_attempt() -> None:
    """The runtime emits the events below in this order, so the sink is driven directly."""
    exporter = InMemorySpanExporter()
    observability = observed(exporter)
    sink: EventSpans = observability.event_sink()

    for reported in (
        event(EventType.WORKFLOW_STARTED, 1, detail="steps=1"),
        event(EventType.STEP_STARTED, 2, step="fetch", attempt=1),
        event(
            EventType.STEP_FAILED,
            3,
            step="fetch",
            attempt=1,
            duration=0.5,
            error_type="RateLimitError",
        ),
        event(EventType.STEP_RETRIED, 4, step="fetch", attempt=1, detail="retrying in 0.05s"),
        event(EventType.STEP_STARTED, 5, step="fetch", attempt=2),
        event(EventType.STEP_SUCCEEDED, 6, step="fetch", attempt=2, duration=0.25),
        event(EventType.WORKFLOW_SUCCEEDED, 7),
    ):
        sink(reported)

    observability.shutdown()

    spans = exporter.get_finished_spans()
    attempts = [span for span in spans if span.name == "step demo.fetch"]
    assert [span.attributes["xyberos.attempt"] for span in attempts] == [1, 2]
    assert [span.status.status_code for span in attempts] == [
        StatusCode.ERROR,
        StatusCode.OK,
    ]

    run = only(spans, "workflow demo")
    retried = [entry for entry in run.events if entry.name == "step_retried"]
    assert len(retried) == 1, "a retry is reported on the span that is still open"
    assert retried[0].attributes is not None
    assert retried[0].attributes["xyberos.event.detail"] == "retrying in 0.05s"
