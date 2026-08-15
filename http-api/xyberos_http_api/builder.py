"""Turn declared operations into typed :class:`~xyberos.contracts.Tool`s.

Each operation becomes a :class:`~xyberos.tools.FunctionTool` whose signature
is derived from the declared parameters. ``FunctionTool`` then handles JSON
schema generation, argument validation, and coercion through
``coerce_arguments`` — so an LLM (or a user) passing ``"10.5"`` for a ``number``
parameter gets it coerced to ``10.5``.
"""

from __future__ import annotations

import inspect
import re
from typing import Any

from xyberos.contracts import Tool
from xyberos.tools import FunctionTool

from .client import HttpClient
from .spec import HttpApiSpec, Operation, Param

_TOKEN_RE = re.compile(r"\[(\d+)\]")


def _safe_identifier(name: str) -> str:
    """Turn an arbitrary param/header name into a valid Python identifier."""
    ident = re.sub(r"\W", "_", name)
    if not ident:
        ident = "param"
    if ident[0].isdigit():
        ident = "_" + ident
    return ident


def make_typed_callable(name: str, params: list[Param], impl: Any) -> Any:
    """Build a callable whose ``__signature__`` matches the declared params.

    ``impl(kwargs)`` receives the validated/coerced arguments as a dict keyed
    by the **declared** param names. ``inspect.signature`` honors
    ``__signature__``, so both :func:`~xyberos.tools.build_json_schema` and
    :func:`~xyberos.tools.coerce_arguments` see the declared, typed signature.
    Parameter names that are not valid Python identifiers (e.g. header names
    like ``X-Trace``) are sanitized for the signature and mapped back.
    """
    mapping: dict[str, str] = {}
    signature_params: list[inspect.Parameter] = []
    for param in params:
        sig_name = param.name if param.name.isidentifier() else _safe_identifier(param.name)
        mapping[sig_name] = param.name
        if param.required:
            signature_params.append(
                inspect.Parameter(
                    sig_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=param.python_type,
                )
            )
        else:
            signature_params.append(
                inspect.Parameter(
                    sig_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=param.default,
                    annotation=param.python_type,
                )
            )
    signature = inspect.Signature(parameters=signature_params)

    def _call(**kwargs: Any) -> Any:
        real = {mapping.get(key, key): value for key, value in kwargs.items()}
        return impl(real)

    _call.__name__ = name
    _call.__qualname__ = name
    _call.__signature__ = signature
    return _call


def extract_path(data: Any, path: str | None) -> Any:
    """Extract a dotted path (with optional ``[index]`` steps) from JSON data."""
    if not path:
        return data
    current = data
    for part in path.split("."):
        match = _TOKEN_RE.search(part)
        key = _TOKEN_RE.sub("", part) if match else part
        if key and isinstance(current, dict):
            current = current.get(key)
        elif key and not isinstance(current, dict):
            return None
        if match and isinstance(current, list):
            try:
                current = current[int(match.group(1))]
            except (IndexError, ValueError):
                return None
    return current


def build_operation_tool(
    spec: HttpApiSpec,
    operation: Operation,
    client: HttpClient,
    *,
    prefix: str = "",
) -> Tool:
    """Build one typed tool for ``operation`` backed by ``client``."""

    def _impl(arguments: dict[str, Any]) -> Any:
        path = operation.path
        query: dict[str, Any] = {}
        body: Any = None
        extra_headers: dict[str, str] = {}
        for param in operation.params:
            if param.name not in arguments:
                continue
            value = arguments[param.name]
            if param.in_ == "path":
                path = path.replace("{" + param.name + "}", str(value))
            elif param.in_ == "query":
                query[param.name] = value
            elif param.in_ == "header":
                extra_headers[param.name] = str(value)
            elif param.in_ == "body":
                body = value
        result = client.request(
            operation.method,
            path,
            query=query,
            body=body,
            headers=extra_headers,
        )
        if operation.response_format == "text":
            return result
        return extract_path(result, operation.response_path)

    name = f"{prefix}{operation.name}" if prefix else operation.name
    callable_func = make_typed_callable(name, list(operation.params), _impl)
    return FunctionTool(name, callable_func, description=operation.description)
