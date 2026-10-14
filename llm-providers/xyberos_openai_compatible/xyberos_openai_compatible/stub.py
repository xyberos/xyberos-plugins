"""A real, small OpenAI-compatible server, so the suite runs without a vendor.

This is a local HTTP service, not a mock of one: the provider under test speaks HTTP to it over a
socket, and the bytes it sends and receives are the bytes a gateway would see. It serves the three
routes an OpenAI-compatible endpoint is judged by — ``POST /v1/chat/completions`` (streamed and not),
``POST /v1/embeddings``, and ``GET /v1/models`` — faithfully enough for the *structural* checks the
conformance suite makes: an assistant message, a streaming stream that ends exactly once, usage
fields that add up, a tool call that names the tool it was given, a structured payload that matches
the schema it was given, and one embedding per input.

``running_stub()`` binds an ephemeral port and is what both the tests and the conformance target
use; ``python -m xyberos_openai_compatible.stub`` binds 59080 for looking at the wire yourself.

This module ships in the distribution rather than living under ``tests/`` because the conformance
target needs it: the compatibility job installs the *published wheel* and holds no credential, so
the only endpoint it can prove this adapter against is one the package serves itself. With
``XYBEROS_OPENAI_BASE_URL`` set, the suite runs against that deployment instead and this server is
never started.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

DEFAULT_PORT = 59080
CHAT_MODEL = "stub-model"
EMBEDDING_MODEL = "stub-embedding-model"
EMBEDDING_WIDTH = 4
"""The width of every stub vector. The suite checks that the width is one non-zero number, not what
the numbers are."""

MODELS_PATH = "/v1/models"
CHAT_PATH = "/v1/chat/completions"
EMBEDDINGS_PATH = "/v1/embeddings"


def vector_for(text: str) -> tuple[float, ...]:
    """Return a deterministic vector for ``text``, so a test can assert it travelled intact.

    The same four numbers the core's fake provider uses — length, checksum, words, vowels — because
    they are plumbing rather than semantics.
    """
    return (
        float(len(text)),
        float(sum(ord(character) for character in text)),
        float(len(text.split())),
        float(sum(1 for character in text.lower() if character in "aeiou")),
    )


def _as_object(value: object) -> Mapping[str, object] | None:
    """Return ``value`` as a string-keyed mapping, or ``None`` when it is not an object.

    Decoded JSON arrives as ``object``, and a bare ``isinstance(..., Mapping)`` narrows to a mapping
    with unknown keys that then spreads through every read. Stating the shape once here is what keeps
    this file readable by a type checker as well as by a person.
    """
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, object], value)


def _as_sequence(value: object) -> Sequence[object] | None:
    """Return ``value`` as an array of elements, or ``None`` when it is not an array."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    return cast(Sequence[object], value)


def _usage(prompt_tokens: int, completion_tokens: int) -> dict[str, int]:
    prompt, completion = max(1, prompt_tokens), max(1, completion_tokens)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _prompt_text(payload: Mapping[str, object]) -> str:
    messages = _as_sequence(payload.get("messages"))
    if not messages:
        return ""
    parts: list[str] = []
    for message in messages:
        entry = _as_object(message)
        if entry is None:
            continue
        content = entry.get("content")
        if isinstance(content, str):
            parts.append(content)
    return " ".join(parts)


def _example_payload(schema: object) -> object:
    """Build a payload that satisfies a schema, which is all a stub can honestly promise."""
    entry = _as_object(schema)
    if entry is None:
        return {}
    kind = entry.get("type")
    if kind == "object" or "properties" in entry:
        properties = _as_object(entry.get("properties")) or {}
        required = _as_sequence(entry.get("required"))
        names = (
            [str(name) for name in required]
            if required
            else [str(name) for name in properties]
        )
        return {name: _example_payload(properties.get(name, {})) for name in names}
    if kind == "array":
        return []
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return True
    if kind == "null":
        return None
    return "stub"


def _requested_schema(payload: Mapping[str, object]) -> object | None:
    """Return the schema a structured request asked for, or ``None`` when it asked for none."""
    response_format = _as_object(payload.get("response_format"))
    if response_format is None:
        return None
    if response_format.get("type") == "json_object":
        return {"type": "object"}
    json_schema = _as_object(response_format.get("json_schema"))
    if json_schema is None:
        return None
    return json_schema.get("schema", {})


def chat_completion(payload: Mapping[str, object]) -> dict[str, object]:
    """Answer one ``POST /v1/chat/completions`` as an OpenAI-compatible service would."""
    model = payload.get("model")
    tools = _as_sequence(payload.get("tools"))
    first_tool = _as_object(tools[0]) if tools else None
    if first_tool is not None:
        declaration = _as_object(first_tool.get("function")) or {}
        name = declaration.get("name")
        message: dict[str, object] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_stub_1",
                    "type": "function",
                    "function": {
                        "name": name if isinstance(name, str) and name else "tool",
                        "arguments": json.dumps(
                            _example_payload(declaration.get("parameters") or {"type": "object"})
                        ),
                    },
                }
            ],
        }
        finish_reason = "tool_calls"
    else:
        schema = _requested_schema(payload)
        content = json.dumps(_example_payload(schema)) if schema is not None else "ok"
        message = {"role": "assistant", "content": content}
        finish_reason = "stop"
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": model if isinstance(model, str) and model else CHAT_MODEL,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": _usage(len(_prompt_text(payload).split()), 1),
    }


def _stream_chunks(completion: Mapping[str, object]) -> list[dict[str, object]]:
    """Split a completion into the chunks an OpenAI-compatible stream sends."""
    choices = _as_sequence(completion["choices"])
    if not choices:
        return []
    choice = _as_object(choices[0])
    if choice is None:
        return []
    message = _as_object(choice.get("message")) or {}
    delta: dict[str, object] = {"role": "assistant"}
    content = message.get("content")
    if content is not None:
        delta["content"] = content
    prefix: dict[str, object] = {
        "id": completion["id"],
        "object": "chat.completion.chunk",
        "created": completion["created"],
        "model": completion["model"],
    }
    return [
        {**prefix, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {
            **prefix,
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": choice.get("finish_reason")}
            ],
        },
        {**prefix, "choices": [], "usage": completion["usage"]},
    ]


def embeddings_response(payload: Mapping[str, object]) -> dict[str, object] | None:
    """Answer one ``POST /v1/embeddings``, or ``None`` when the inputs are unusable."""
    raw = payload.get("input")
    if isinstance(raw, str):
        inputs = [raw]
    else:
        declared = _as_sequence(raw)
        if not declared or not all(isinstance(item, str) for item in declared):
            return None
        inputs = [str(item) for item in declared]
    model = payload.get("model")
    return {
        "object": "list",
        "model": model if isinstance(model, str) and model else EMBEDDING_MODEL,
        "data": [
            {"object": "embedding", "index": index, "embedding": list(vector_for(text))}
            for index, text in enumerate(inputs)
        ],
        "usage": _usage(sum(len(text.split()) for text in inputs), 0),
    }


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "xyberos-stub/0.1"

    def log_message(self, format: str, *args: object) -> None:
        """Stay quiet: a test's output is the test's business."""

    def do_GET(self) -> None:  # noqa: N802 - the name http.server calls
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == MODELS_PATH:
            self._send_json(
                {
                    "object": "list",
                    "data": [
                        {"id": CHAT_MODEL, "object": "model", "owned_by": "xyberos"},
                        {"id": EMBEDDING_MODEL, "object": "model", "owned_by": "xyberos"},
                    ],
                }
            )
            return
        self._not_found(path)

    def do_POST(self) -> None:  # noqa: N802 - the name http.server calls
        path = self.path.split("?", 1)[0].rstrip("/")
        payload = self._read_payload()
        if payload is None:
            return
        if path == CHAT_PATH:
            if payload.get("stream") is True:
                self._send_stream(chat_completion(payload))
                return
            self._send_json(chat_completion(payload))
            return
        if path == EMBEDDINGS_PATH:
            body = embeddings_response(payload)
            if body is None:
                self._send_json(
                    {"error": {"message": "input must be text", "type": "invalid_request_error"}},
                    status=400,
                )
                return
            self._send_json(body)
            return
        self._not_found(path)

    def _not_found(self, path: str) -> None:
        self._send_json(
            {"error": {"message": f"no route for {path}", "type": "invalid_request_error"}},
            status=404,
        )

    def _read_payload(self) -> dict[str, object] | None:
        length = self.headers.get("Content-Length")
        raw = self.rfile.read(int(length)) if length and length.isdigit() else b""
        if not raw:
            return {}
        try:
            decoded: object = json.loads(raw)
        except ValueError:
            self._send_json(
                {"error": {"message": "the body is not JSON", "type": "invalid_request_error"}},
                status=400,
            )
            return None
        data = _as_object(decoded)
        if data is None:
            self._send_json(
                {"error": {"message": "the body is not an object", "type": "invalid_request_error"}},
                status=400,
            )
            return None
        return dict(data)

    def _send_json(self, body: Mapping[str, object], *, status: int = 200) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("openai-version", "2020-10-01")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_stream(self, completion: Mapping[str, object]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        # A stream has no length, so it is delimited by closing the connection, which is also what
        # tells an OpenAI-compatible client that the stream is over.
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        for chunk in _stream_chunks(completion):
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


@dataclass
class StubServer:
    """A running stub service, and the base URL that reaches it."""

    server: ThreadingHTTPServer
    thread: threading.Thread

    @property
    def port(self) -> int:
        """Return the port the server actually bound, which is ephemeral in the tests."""
        return int(self.server.server_address[1])

    @property
    def base_url(self) -> str:
        """Return the ``/v1`` root an OpenAI-compatible client should be pointed at."""
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self) -> None:
        """Stop serving and wait for the serving thread to finish."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@contextlib.contextmanager
def running_stub(port: int = 0) -> Generator[StubServer]:
    """Serve the stub on ``port`` (0 for an ephemeral one) until the block exits."""
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="xyberos-stub", daemon=True)
    thread.start()
    stub = StubServer(server=server, thread=thread)
    try:
        yield stub
    finally:
        stub.stop()


def main() -> int:
    """Serve the stub on 59080 until interrupted, for looking at the wire yourself."""
    with running_stub(DEFAULT_PORT) as stub:
        print(f"serving an OpenAI-compatible stub at {stub.base_url}")
        print("point XYBEROS_OPENAI_BASE_URL at it to run the conformance module against this server")
        try:
            stub.thread.join()
        except KeyboardInterrupt:  # pragma: no cover - how an operator stops it
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover - the script an operator runs
    raise SystemExit(main())
