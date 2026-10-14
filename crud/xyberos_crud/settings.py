"""The limits and the operator vocabulary one CRUD query is answered under.

What a deployment must decide — the largest page it will serve, how large a page is when the request
does not say, and which operator names may reach the database — is a value passed to
:func:`~xyberos_crud.statement.apply_query`, never a new root key in ``Settings``: a distribution
beside the framework does not get to widen the configuration an application already owns.

The operator names are the vocabulary of the query string, so they are listed here rather than
invented at the call site: ``field__gte=30`` means whatever ``gte`` means in this module and nowhere
else.
"""

from __future__ import annotations

from dataclasses import dataclass

from xyberos.errors import ConfigurationError

EQ = "eq"
NE = "ne"
LT = "lt"
LTE = "lte"
GT = "gt"
GTE = "gte"
IN = "in"
CONTAINS = "contains"
STARTSWITH = "startswith"
IS_NULL = "is_null"

DEFAULT_OPERATORS: frozenset[str] = frozenset(
    {EQ, NE, LT, LTE, GT, GTE, IN, CONTAINS, STARTSWITH, IS_NULL}
)
"""Every operator this package implements, and therefore the default allowlist.

It doubles as the set an operator name is checked against when one is read off a query string, so a
name this package does not implement is refused where the request is parsed rather than at the
database.
"""


@dataclass(frozen=True)
class CrudSettings:
    """The bounds a deployment sets on every query it answers."""

    max_limit: int = 100
    """The most rows a page may hold. A request asking for more is clamped, never refused."""

    default_limit: int = 20
    """The page size when the request does not name one."""

    allowed_operators: frozenset[str] = DEFAULT_OPERATORS
    """Which of the operators above a caller may use."""

    def __post_init__(self) -> None:
        if self.max_limit < 1:
            raise ConfigurationError(f"max_limit must be positive, got {self.max_limit}")
        if self.default_limit < 1:
            raise ConfigurationError(f"default_limit must be positive, got {self.default_limit}")
        if self.default_limit > self.max_limit:
            raise ConfigurationError(
                f"default_limit {self.default_limit} must not exceed max_limit {self.max_limit}"
            )
        if not self.allowed_operators:
            raise ConfigurationError("allowed_operators must name at least one operator")
        unknown = sorted(self.allowed_operators - DEFAULT_OPERATORS)
        if unknown:
            known = ", ".join(sorted(DEFAULT_OPERATORS))
            raise ConfigurationError(
                f"unknown operator(s) {', '.join(unknown)}; known operators are: {known}"
            )
