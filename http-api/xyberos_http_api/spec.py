"""Declarative REST API specification for the HTTP/API connector.

A spec is authored as a Python ``dict``, a JSON file, or a YAML file (the YAML
dependency is imported lazily). It describes a ``base_url``, optional headers,
optional auth, optional rate limiting, and a list of *operations* — each of
which becomes one typed :class:`~xyberos.contracts.Tool`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xyberos.exceptions.provider import ProviderError

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}

#: Where a parameter value is placed on the wire.
_PARAM_LOCATIONS = ("query", "path", "header", "body")
_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


@dataclass(frozen=True)
class Param:
    """One declared operation parameter."""

    name: str
    in_: str = "query"  # query | path | header | body
    type: str = "string"  # string | integer | number | boolean | array | object
    required: bool = False
    description: str = ""
    default: Any = None

    @property
    def python_type(self) -> type:
        return _TYPE_MAP.get(self.type, str)


@dataclass(frozen=True)
class Operation:
    """One declared API operation (an HTTP method + path + typed params)."""

    name: str
    method: str = "GET"
    path: str = "/"
    description: str = ""
    params: tuple[Param, ...] = ()
    response_format: str = "json"  # json | text
    response_path: str | None = None  # dotted path extracted from a JSON body


@dataclass(frozen=True)
class AuthSpec:
    """Authentication strategy. Secrets come from ``*_env`` variables when set."""

    type: str = "none"  # none | api_key | bearer | basic | oauth2
    # api_key
    key_name: str = "api_key"
    key_in: str = "header"  # header | query
    value: str | None = None
    env: str | None = None
    # bearer
    token: str | None = None
    token_env: str | None = None
    # basic
    username: str | None = None
    username_env: str | None = None
    password: str | None = None
    password_env: str | None = None
    # oauth2 (client_credentials)
    token_url: str | None = None
    client_id: str | None = None
    client_id_env: str | None = None
    client_secret: str | None = None
    client_secret_env: str | None = None
    scope: str | None = None


@dataclass(frozen=True)
class RateLimitSpec:
    """Token-bucket rate limiting, backed by ``xyberos.utils.resilience.RateLimiter``."""

    calls_per_second: float = 1.0
    burst: int = 1


@dataclass
class HttpApiSpec:
    """A complete declarative API connection."""

    name: str
    base_url: str
    operations: list[Operation] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    auth: AuthSpec = field(default_factory=AuthSpec)
    rate_limit: RateLimitSpec | None = None
    timeout: float = 30.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HttpApiSpec":
        """Build a spec from a plain mapping, validating required fields."""
        name = data.get("name")
        base_url = data.get("base_url")
        if not name:
            raise ValueError("spec 'name' is required")
        if not base_url:
            raise ValueError("spec 'base_url' is required")

        operations: list[Operation] = []
        for index, raw in enumerate(data.get("operations") or ()):
            operations.append(_operation_from_dict(raw, index))

        auth = _auth_from_dict(data.get("auth") or {})
        rate_limit = _rate_limit_from_dict(data.get("rate_limit"))
        return cls(
            name=str(name),
            base_url=str(base_url).rstrip("/"),
            operations=operations,
            headers=dict(data.get("headers") or {}),
            auth=auth,
            rate_limit=rate_limit,
            timeout=float(data.get("timeout", 30.0)),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "HttpApiSpec":
        """Load a spec from a JSON or YAML file (YAML imported lazily)."""
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml  # optional dependency
            except ImportError as exc:  # pragma: no cover - environment specific
                raise ProviderError(
                    "the 'PyYAML' package is required to load YAML specs; "
                    "install it with 'pip install PyYAML' or use a JSON spec"
                ) from exc
            data: Any = yaml.safe_load(text)
        else:
            data = json.loads(text)
        return cls.from_dict(data)


def _operation_from_dict(raw: Mapping[str, Any], index: int) -> Operation:
    name = raw.get("name")
    if not name:
        raise ValueError(f"operations[{index}] is missing a 'name'")
    method = str(raw.get("method", "GET")).upper()
    if method not in _METHODS:
        raise ValueError(f"operation '{name}' has unsupported method '{method}'")
    params: list[Param] = []
    for param_index, p in enumerate(raw.get("params") or ()):
        param_name = p.get("name")
        if not param_name:
            raise ValueError(f"operation '{name}' params[{param_index}] is missing a 'name'")
        location = str(p.get("in", "query")).lower()
        if location not in _PARAM_LOCATIONS:
            raise ValueError(f"operation '{name}' param '{param_name}' has bad 'in': {location}")
        params.append(
            Param(
                name=str(param_name),
                in_=location,
                type=str(p.get("type", "string")).lower(),
                required=bool(p.get("required", False)),
                description=str(p.get("description", "")),
                default=p.get("default"),
            )
        )
    return Operation(
        name=str(name),
        method=method,
        path=str(raw.get("path", "/")),
        description=str(raw.get("description", "")),
        params=tuple(params),
        response_format=str(raw.get("response_format", "json")).lower(),
        response_path=raw.get("response_path"),
    )


def _auth_from_dict(data: Mapping[str, Any]) -> AuthSpec:
    auth_type = str(data.get("type", "none")).lower()
    fields: dict[str, Any] = {"type": auth_type}
    if auth_type == "api_key":
        fields.update(
            key_name=str(data.get("key_name", "api_key")),
            key_in=str(data.get("in", "header")).lower(),
            value=data.get("value"),
            env=data.get("env"),
        )
    elif auth_type == "bearer":
        fields.update(token=data.get("token"), token_env=data.get("env") or data.get("token_env"))
    elif auth_type == "basic":
        fields.update(
            username=data.get("username"),
            username_env=data.get("username_env"),
            password=data.get("password"),
            password_env=data.get("password_env"),
        )
    elif auth_type == "oauth2":
        fields.update(
            token_url=data.get("token_url"),
            client_id=data.get("client_id"),
            client_id_env=data.get("client_id_env"),
            client_secret=data.get("client_secret"),
            client_secret_env=data.get("client_secret_env"),
            scope=data.get("scope"),
        )
    elif auth_type != "none":
        raise ValueError(f"unsupported auth type: {auth_type}")
    return AuthSpec(**fields)


def _rate_limit_from_dict(data: Mapping[str, Any] | None) -> RateLimitSpec | None:
    if not data:
        return None
    return RateLimitSpec(
        calls_per_second=float(data.get("calls_per_second", 1.0)),
        burst=int(data.get("burst", 1)),
    )


def load_spec(source: Any) -> HttpApiSpec | list[HttpApiSpec]:
    """Load one or more specs from a dict, JSON/YAML file path, or file text."""
    if isinstance(source, (str, Path)):
        return HttpApiSpec.from_file(source)
    if isinstance(source, list):
        return [HttpApiSpec.from_dict(item) for item in source]
    if isinstance(source, Mapping):
        return HttpApiSpec.from_dict(source)
    raise TypeError("spec must be a mapping, a list of mappings, or a path to a JSON/YAML file")
