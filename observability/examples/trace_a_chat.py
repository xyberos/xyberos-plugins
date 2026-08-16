"""Trace a chat session with the observability plugin.

The default OpenTelemetry exporter keeps spans in memory (InMemorySpanExporter)
so you can inspect them; run with ``--langfuse`` to POST real traces to a
Langfuse instance instead.

Usage:
    python examples/trace_a_chat.py
    python examples/trace_a_chat.py --langfuse --public-key pk-lf-xxx --secret-key sk-lf-xxx
"""

from __future__ import annotations

import argparse
import os

from xyberos import create_app

from xyberos_observability import LangfuseExporter, ObservabilityPlugin, OpenTelemetryExporter, PrometheusExporter


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace a chat with the observability plugin.")
    parser.add_argument("--langfuse", action="store_true", help="POST traces to Langfuse (needs keys/env)")
    parser.add_argument("--public-key", default=os.environ.get("LANGFUSE_PUBLIC_KEY"))
    parser.add_argument("--secret-key", default=os.environ.get("LANGFUSE_SECRET_KEY"))
    parser.add_argument("--host", default=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"))
    parser.add_argument("--prometheus", action="store_true", help="expose prometheus metrics")
    args = parser.parse_args()

    exporters = [OpenTelemetryExporter()]
    if args.prometheus:
        exporters.append(PrometheusExporter())
    if args.langfuse:
        exporters.append(LangfuseExporter(args.public_key, args.secret_key, host=args.host))

    app = create_app()
    app.load_plugin(ObservabilityPlugin(exporters=exporters))

    print("> hello, who are you?")
    reply = app.chat("hello, who are you?")
    print(f"< {reply}")

    app.unload_plugin("observability")

    otel = next(e for e in exporters if isinstance(e, OpenTelemetryExporter))
    print(f"\n{len(otel.spans())} spans captured:")
    for span in otel.spans():
        print(f"  - {span.name}")

    prom = next((e for e in exporters if isinstance(e, PrometheusExporter)), None)
    if prom is not None:
        print(f"\n'brain.response_produced' counter = {prom.value('brain.response_produced')}")


if __name__ == "__main__":
    main()
