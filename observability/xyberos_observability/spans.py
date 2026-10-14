"""The event sink: workflow and step events become spans.

The runtime reports every state transition as a
:class:`~xyberos.execution.events.WorkflowEvent` handed to the :data:`~xyberos.execution.events.EventSink`
the caller supplies — ``run(on_event=...)``. This module is one such sink and nothing more: it
subscribes, so no runtime internal is patched, no private module is imported, and a runtime that
emits events correctly is traced by construction.

Naming is a contract, because it is what a dashboard groups by:

* a workflow span is ``workflow <name>``, opened by ``workflow_started`` and closed by the run's
  terminal event;
* a step span is ``step <workflow>.<step>``, one per attempt, opened by ``step_started`` and closed
  by ``step_succeeded``, ``step_failed``, ``step_skipped``, ``step_timed_out``, or
  ``step_cancelled``, as a child of its run's workflow span;
* ``step_retried`` becomes an event on the workflow span, because the attempt it retries has already
  closed its own span and rewriting a span that has been exported is not possible.

Every span carries the correlation id the runtime bound at the start of the run, under the same
attribute the request span uses, which is what lets a log line and a span be joined.
"""

from __future__ import annotations

from opentelemetry.trace import Span, Status, StatusCode, Tracer, set_span_in_context
from opentelemetry.util.types import AttributeValue

from xyberos import EventType, WorkflowEvent, get_correlation_id

__all__ = ["CORRELATION_ID_ATTRIBUTE", "EventSpans", "step_span_name", "workflow_span_name"]

CORRELATION_ID_ATTRIBUTE = "xyberos.correlation_id"
"""The attribute that makes a log line and a span agree: the id the runtime already mints."""

_WORKFLOW_ENDED = frozenset(
    {
        EventType.WORKFLOW_SUCCEEDED,
        EventType.WORKFLOW_FAILED,
        EventType.WORKFLOW_TIMED_OUT,
        EventType.WORKFLOW_CANCELLED,
    }
)

_STEP_ENDED = frozenset(
    {
        EventType.STEP_SUCCEEDED,
        EventType.STEP_FAILED,
        EventType.STEP_SKIPPED,
        EventType.STEP_TIMED_OUT,
        EventType.STEP_CANCELLED,
    }
)

#: A run, or an attempt, that ended badly is an error span. A skip is a decision, not a failure.
_FAILED = frozenset(
    {
        EventType.WORKFLOW_FAILED,
        EventType.WORKFLOW_TIMED_OUT,
        EventType.WORKFLOW_CANCELLED,
        EventType.STEP_FAILED,
        EventType.STEP_TIMED_OUT,
        EventType.STEP_CANCELLED,
    }
)


def workflow_span_name(workflow: str) -> str:
    """Return the name one run's span is given."""
    return f"workflow {workflow}"


def step_span_name(workflow: str, step: str) -> str:
    """Return the name one step attempt's span is given."""
    return f"step {workflow}.{step}"


class EventSpans:
    """One run's events, as spans.

    Pass a fresh sink to each run — ``run(on_event=EventSpans(tracer))`` — because a sink owns the
    spans it opened, and ``WorkflowEvent`` carries no run identifier to attribute an event by. A
    sink shared by two concurrent runs of the same workflow would have to guess which run an event
    belongs to, and this one does not guess.
    """

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._workflow: Span | None = None
        self._steps: dict[tuple[str, str], Span] = {}

    def __call__(self, event: WorkflowEvent) -> None:
        """Report one event.

        A sink runs on the execution path, so this never blocks and never raises: an event type a
        later runtime adds is ignored rather than breaking the run that emitted it.
        """
        event_type = event.type
        if event_type is EventType.WORKFLOW_STARTED:
            self._workflow = self._open(workflow_span_name(event.workflow), event, parent=None)
        elif event_type in _WORKFLOW_ENDED:
            opened, self._workflow = self._workflow, None
            self._close(workflow_span_name(event.workflow), event, opened)
        elif event_type is EventType.STEP_STARTED:
            self._steps[_step_key(event)] = self._open(
                step_span_name(event.workflow, event.step or ""), event, parent=self._workflow
            )
        elif event_type in _STEP_ENDED:
            opened = self._steps.pop(_step_key(event), None)
            self._close(step_span_name(event.workflow, event.step or ""), event, opened)
        elif event_type is EventType.STEP_RETRIED:
            self._record_retry(event)

    def _open(self, name: str, event: WorkflowEvent, *, parent: Span | None) -> Span:
        """Start a span, a child of the run's workflow span when that span is still open."""
        if parent is not None:
            return self._tracer.start_span(
                name, context=set_span_in_context(parent), attributes=_attributes(event)
            )
        return self._tracer.start_span(name, attributes=_attributes(event))

    def _close(self, name: str, event: WorkflowEvent, opened: Span | None) -> None:
        """Set the terminal attributes and status, and end the span.

        An event that arrives without the one that opens its span still becomes a span, so nothing
        on the event stream is invisible: a step a branch never reached is exactly that case, and it
        is the shape of a run a reader most wants to see.
        """
        span = self._tracer.start_span(name) if opened is None else opened
        for key, value in _attributes(event).items():
            span.set_attribute(key, value)
        span.set_status(Status(StatusCode.ERROR) if event.type in _FAILED else Status(StatusCode.OK))
        span.end()

    def _record_retry(self, event: WorkflowEvent) -> None:
        """Record the retry on whichever span is still open."""
        attributes = _attributes(event)
        for span in (self._steps.get(_step_key(event)), self._workflow):
            if span is not None and span.is_recording():
                span.add_event("step_retried", attributes=attributes)


def _step_key(event: WorkflowEvent) -> tuple[str, str]:
    return (event.workflow, event.step or "")


def _attributes(event: WorkflowEvent) -> dict[str, AttributeValue]:
    """The event, as span attributes: identifiers, attempts, and timings, never a payload."""
    attributes: dict[str, AttributeValue] = {
        "xyberos.event.type": event.type.value,
        "xyberos.event.sequence": event.sequence,
        "xyberos.workflow": event.workflow,
        "xyberos.workflow.version": event.version,
    }
    if event.step is not None:
        attributes["xyberos.step"] = event.step
    if event.attempt is not None:
        attributes["xyberos.attempt"] = event.attempt
    if event.duration is not None:
        attributes["xyberos.duration"] = event.duration
    if event.detail is not None:
        attributes["xyberos.event.detail"] = event.detail
    if event.error_type is not None:
        attributes["xyberos.error_type"] = event.error_type
    correlation_id = (
        event.correlation_id if event.correlation_id is not None else get_correlation_id()
    )
    if correlation_id is not None:
        attributes[CORRELATION_ID_ATTRIBUTE] = correlation_id
    return attributes
