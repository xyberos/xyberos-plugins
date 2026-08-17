# xyberos-observability (M10)

Observability/telemetry exporters for Xyberos. Turns the runtime's event stream
into traces and metrics for **OpenTelemetry**, **Prometheus**, **Langfuse**, and
**Sentry** — satisfying RFC-0019 Track L, milestone M10.

## Install

```bash
pip install xyberos-observability     # from PyPI
```

Optional extras (from PyPI):

```bash
pip install "xyberos-observability[otel]"        # opentelemetry-sdk (in-memory spans by default)
pip install "xyberos-observability[prometheus]"  # prometheus-client
pip install "xyberos-observability[sentry]"      # sentry-sdk
```

Development (editable, from this repo):

```bash
pip install -e ./observability
pip install -e "./observability[otel]"
pip install -e "./observability[prometheus]"
pip install -e "./observability[sentry]"
```

## How it works

Xyberos emits events (`runtime.request_started`, `brain.response_produced`,
`memory.stored`, ...) on its `EventBus`. This plugin attaches an
`EventRecorder` that forwards each event to the configured exporters:

| Exporter | Destination | What it does |
| --- | --- | --- |
| `OpenTelemetryExporter` | OTel span pipeline | One span per event, named `event.name`, with `event.*` attributes (plus `event.prompt`). Defaults to an `InMemorySpanExporter` so traces are inspectable without a collector. |
| `PrometheusExporter` | Prometheus registry | `xyberos_events_total{event="..."}` counter, one per event name. |
| `LangfuseExporter` | Langfuse `/api/public/ingestion` | One `observation-create` item per event with `name`, `input` (prompt) and `output` (event data). Basic auth with `public_key:secret_key`. |
| `SentryExporter` | Sentry SDK | Adds a breadcrumb per event; captures a message for failures (`runtime.request_failed`, `brain.error`). |

## Usage

```python
from xyberos import create_app
from xyberos_observability import ObservabilityPlugin, OpenTelemetryExporter

app = create_app()
app.load_plugin(ObservabilityPlugin(exporters=[OpenTelemetryExporter()]))

reply = app.chat("hello")          # emits events -> spans
```

Select exporters by environment variable (comma-separated) instead:

```bash
export OBSERVABILITY_EXPORTERS=otel,prometheus,langfuse,sentry
```

```python
from xyberos_observability import ObservabilityPlugin

app.load_plugin(ObservabilityPlugin())
```

For Langfuse, set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and
`LANGFUSE_HOST` (defaults `https://cloud.langfuse.com`).

## Example

```bash
python examples/trace_a_chat.py                       # inspect in-memory spans
python examples/trace_a_chat.py --prometheus          # also track a counter
python examples/trace_a_chat.py --langfuse            # POST traces to Langfuse
```

## Tests

```bash
python -m pytest observability/tests -q
```

Tests use injectable transports / in-memory exporters, so nothing touches the
network or a real collector. The DoD test (`tests/test_plugin.py`) runs
`app.chat(...)` and asserts a trace lands in OTel and Langfuse.
