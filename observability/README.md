# xyberos-observability

**A logging handler and OpenTelemetry spans for Xyberos, fed by the runtime's own event sink.**

**None of the 1.x exporters return.** The published `0.1.2` bundled four of them — Prometheus,
Langfuse, Sentry, and a `xyberos.plugins` entry point the 1.x runtime discovered at import time — and
every one of them is gone, along with the entry point. What this version configures is a logging
handler and spans: one explicit call that installs the handler, a level, a format, and the runtime's
own `ContextLogFilter`, plus spans made from the runtime's own events and from the correlation id the
HTTP adapter already mints. The 1.x package stays on the index at `0.1.2` for anyone still on the 1.x
line; its source stays in this repository's history.

The runtime configures no logging and exports no telemetry of its own, deliberately: a library that
installs a handler fights the application that embeds it
([observability](https://docs.xyberos.com/production/observability/)). This package is the other
half, and it is a *distribution* because the wiring is more than a snippet: a sink for the runtime's
event types, a naming contract a dashboard can group by, and a request span that agrees with the log
line beside it.

## Install

```bash
pip install xyberos-observability
```

Where the spans go is yours: this package depends on the OpenTelemetry API and SDK and on nothing
else, so an OTLP exporter, a console exporter, or a collector client is an object you pass.

## Configure it

One object, one call, one place to stop. Nothing here patches a runtime internal, and nothing starts
a thread.

```python
from starlette.middleware import Middleware
from xyberos.http import HttpAdapter
from xyberos_observability import Observability, ObservabilitySettings, RequestSpanMiddleware

observability = Observability(ObservabilitySettings(service="checkout"), exporter=exporter)
observability.configure_logging()  # handler, level, format, and ContextLogFilter

adapter = HttpAdapter(
    app,
    middleware=[Middleware(RequestSpanMiddleware, tracer=observability.tracer)],
)
await workflow.run(on_event=observability.event_sink())  # a fresh sink per run
...
observability.shutdown()  # removes the handler, flushes, shuts the provider down
```

`configure_logging` returns a `LoggingSetup`, which is what an application that wants to control the
lifetime itself asks for:

```python
from xyberos_observability import ObservabilitySettings, configure_logging

setup = configure_logging(ObservabilitySettings(level="INFO", logger="xyberos"))
...
setup.shutdown()  # detaches the handler and gives the level back
```

The settings are a frozen dataclass, and they refuse what would fail later: a level that is not a
logging level, an empty service name, a logger name that is not a dotted identifier, and a format
string that cannot be rendered against a log record all raise `ConfigurationError` at construction.
The settings also arrive through a `Plugin`'s `config_type`, for an application that composes in
sections:

```python
app.add_plugin(ObservabilityPlugin())              # [plugins.observability] in xyberos.toml
app.add_plugin(ObservabilityPlugin(), config={"level": "DEBUG"})
observability = await app.resolve(Observability)
```

## What the spans are

Spans come from three places, and each has a name and a small set of attributes; a payload never
appears in one.

| Span | Opened by | Name | Attributes |
| --- | --- | --- | --- |
| one request | `RequestSpanMiddleware`, which the adapter's own correlation middleware has already given an id | `<METHOD> <path>` | `http.request.method`, `url.path`, `http.response.status_code`, `xyberos.correlation_id` |
| one run | `workflow_started`, closed by the run's terminal event | `workflow <name>` | `xyberos.workflow`, `xyberos.workflow.version`, `xyberos.event.type`, `xyberos.event.sequence`, `xyberos.correlation_id` |
| one attempt | `step_started`, closed by `step_succeeded`, `step_failed`, `step_skipped`, `step_timed_out`, or `step_cancelled` | `step <workflow>.<step>` | the run's attributes plus `xyberos.step`, `xyberos.attempt`, and `xyberos.duration`, `xyberos.error_type` where the event carries them |

Three decisions are worth naming:

- **One sink per run.** `event_sink()` returns a fresh sink because a sink owns the spans it opened
  and `WorkflowEvent` carries no run identifier; passing one sink to two concurrent runs of the same
  workflow would mean guessing which run an event belongs to, and this package does not guess.
- **`step_retried` is an event on the run's span**, not a rewrite of the failed attempt's span: the
  attempt's span is closed, and a span that has left the process cannot be edited.
- **A 5xx is an error and a 4xx is not.** A client asking for something that is not there is not a
  server fault, so a 410 is a `OK` span with a `410` status code attribute rather than an error. The
  span carries the same correlation id `ContextLogFilter` puts on the log line, so
  `{'correlation_id': 'req-1'}` in a log and `xyberos.correlation_id=req-1` on a span are one request.

## What it does not do

- **No Prometheus, Langfuse, or Sentry.** They were the 1.x package's reason to exist and they are
  not this one's. Metrics, LLM tracing, and error reporting are three more exports of the same data,
  and each belongs to the library that owns its protocol.
- **No plugin entry point.** `xyberos` never scans for plugins — entry-point loading means a
  dependency can change what a process does at import time — so this package is added explicitly, by
  name, in the composition root.
- **No configuration of the runtime's logging.** It installs a handler on the logger you name (the
  root logger by default), sets that logger's level, and adds `ContextLogFilter` to the handler.
  Which `xyberos.*` namespace is at which level stays a deployment decision.
- **No hidden thread and no global provider.** Spans leave through `SimpleSpanProcessor`; a
  deployment that wants batching builds its own `TracerProvider` and passes it as `tracer_provider`.
  `trace.set_tracer_provider` is never called.
- **No collector.** Without an exporter the spans are created, timed, and statused, and then dropped.
  Opening a socket the application did not ask for is worse than losing spans.
- **No `conformance.py`.** The catalogue keeps this name `planned` because the core ships no
  conformance suite for this seam: there is no shipped assertion a handler and a span can be held to
  from outside, so the tests in this package are the gate.

## Tests

```bash
python -m pytest tests -q
```

Everything runs offline against the in-memory span exporter, and one test is the evidence the plan
asks for: a handler configured through this package still redacts a value the runtime classified as
a secret, with the same handler rendering the same value when the runtime has not classified it, so
the redaction is provably the runtime's and not a filter this package happens to apply.
