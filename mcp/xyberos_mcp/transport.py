"""MCP transports: stdio (local servers) and streamable HTTP (remote).

Both speak JSON-RPC 2.0 with newline-delimited/HTTP framing. Requests are
correlated by ``id`` through a thread-safe waiter; a reader thread (stdio) or
the HTTP response body carries the reply. A request that exceeds ``timeout``
raises :class:`~xyberos_mcp.McpTimeoutError`.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any

from .errors import McpError, McpTimeoutError
from .http import RequestTransport, default_request


class _Waiter:
    """One outstanding request correlated by JSON-RPC id."""

    def __init__(self, timeout: float) -> None:
        self._event = threading.Event()
        self._message: dict[str, Any] | None = None
        self._timeout = timeout

    def set_message(self, message: dict[str, Any]) -> None:
        self._message = message
        self._event.set()

    def wait(self) -> dict[str, Any]:
        if not self._event.wait(self._timeout):
            raise McpTimeoutError(f"request timed out after {self._timeout}s")
        assert self._message is not None
        return self._message


class StdioTransport:
    """Speaks MCP over a local subprocess's stdin/stdout (JSON-RPC per line).

    The command is launched with ``shell=False`` (never shell-interpolated),
    isolated into a new session, and optionally a working directory / env.
    """

    def __init__(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._command = list(command)
        self._env = env
        self._cwd = cwd
        self._timeout = timeout
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._pending: dict[int, _Waiter] = {}
        self._lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=self._env,
            cwd=self._cwd,
            shell=False,
            **kwargs,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def request(self, id: int, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        waiter = _Waiter(self._timeout)
        with self._lock:
            self._pending[id] = waiter
        self._send({"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})
        return waiter.wait()

    def notify(self, method: str, params: dict[str, Any] | None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        process = self._process
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass
            try:
                process.wait(timeout=5)
            except Exception:
                process.kill()
            self._process = None

    # -- internals ----------------------------------------------------------

    def _send(self, message: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise McpError("transport is not started")
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def _read_loop(self) -> None:
        assert self._process is not None
        stream = self._process.stdout
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            message_id = message.get("id")
            if message_id is None:
                continue  # notifications are not tracked by this client
            with self._lock:
                waiter = self._pending.pop(message_id, None)
            if waiter is not None:
                waiter.set_message(message)


class HttpTransport:
    """Speaks MCP over streamable HTTP (POST JSON-RPC to ``url``).

    Handles both a plain ``application/json`` response and an SSE
    (``text/event-stream``) response, extracting the message matching the
    request id.
    """

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        request: RequestTransport | None = None,
    ) -> None:
        self._url = url
        self._headers = dict(headers or {})
        self._timeout = timeout
        self._request = request or default_request

    def start(self) -> None:
        pass  # HTTP is stateless per request

    def request(self, id: int, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        request_headers.update(self._headers)
        status, body = self._request(
            "POST",
            self._url,
            json_body=payload,
            headers=request_headers,
            timeout=self._timeout,
        )
        if isinstance(body, dict):
            return body
        messages = _parse_sse(body)
        for message in messages:
            if message.get("id") == id:
                return message
        raise McpError(f"no response for id {id} (status {status})")

    def notify(self, method: str, params: dict[str, Any] | None) -> None:
        # Streamable HTTP notifications are fire-and-forget POSTs.
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._request("POST", self._url, json_body=payload, timeout=self._timeout)

    def close(self) -> None:
        pass


def _parse_sse(text: str) -> list[dict[str, Any]]:
    """Parse ``text/event-stream`` data blocks into JSON messages."""
    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif line.strip() == "" and data_lines:
            _push_sse(messages, data_lines)
            data_lines = []
    if data_lines:
        _push_sse(messages, data_lines)
    return messages


def _push_sse(messages: list[dict[str, Any]], data_lines: list[str]) -> None:
    payload = "\n".join(data_lines)
    try:
        messages.append(json.loads(payload))
    except json.JSONDecodeError:
        pass
