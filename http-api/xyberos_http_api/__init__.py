"""Generic HTTP/API connector plugin (RFC-0019, M2).

"Point at any REST API, get typed tools." A declarative spec (JSON / YAML /
Python ``dict``) describes a ``base_url``, optional auth, optional rate
limiting, and one *operation* per endpoint. Each operation becomes a typed
:class:`~xyberos.contracts.Tool` whose parameters are validated and coerced
through :class:`~xyberos.tools.FunctionTool`.

Everything here builds on the public ``xyberos`` API only — no runtime
dependencies beyond the standard library.
"""

from .builder import build_operation_tool
from .client import HttpClient
from .errors import HttpApiError
from .plugin import HttpApiPlugin
from .spec import AuthSpec, HttpApiSpec, Operation, Param, RateLimitSpec, load_spec

__all__ = [
    "AuthSpec",
    "HttpApiError",
    "HttpApiPlugin",
    "HttpApiSpec",
    "HttpClient",
    "Operation",
    "Param",
    "RateLimitSpec",
    "build_operation_tool",
    "load_spec",
]
