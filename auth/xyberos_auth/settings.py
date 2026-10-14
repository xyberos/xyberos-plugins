"""Key material and the checks an assertion must pass, from the environment or an explicit object.

Nothing here reads a configuration file. Key material is the one thing that must never be committed,
so it arrives as an explicit frozen object or through ``XYBEROS_AUTH_*`` variables — the same
precedence the rest of Xyberos uses for a secret, applied to a package that has no file of its own.

Two decisions are made here rather than left to a default, because both have the same failure mode —
an assertion minted for something else verifying here:

* **An audience is required.** An assertion that names no audience, on both sides, is replayable
  against every service that shares the key, so an empty ``audience`` is refused at construction.
* **A secret and a JWKS are mutually exclusive.** Accepting both would let an assertion's own header
  decide which key verified it, which is the algorithm-confusion class of bug rather than a feature.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, cast

from xyberos.errors import ConfigurationError

from xyberos_auth.jwt import (
    ASYMMETRIC_ALGORITHMS,
    SHARED_SECRET_ALGORITHMS,
    SUPPORTED_ALGORITHMS,
    normalize_jwks,
)

#: The variables a deployment sets instead of passing an explicit settings object.
ENV_PREFIX: Final = "XYBEROS_AUTH_"
ENV_AUDIENCE: Final = f"{ENV_PREFIX}AUDIENCE"
ENV_ISSUER: Final = f"{ENV_PREFIX}ISSUER"
ENV_SECRET: Final = f"{ENV_PREFIX}SECRET"
ENV_JWKS: Final = f"{ENV_PREFIX}JWKS"
ENV_ALGORITHMS: Final = f"{ENV_PREFIX}ALGORITHMS"
ENV_LEEWAY: Final = f"{ENV_PREFIX}LEEWAY"


@dataclass(frozen=True)
class AuthSettings:
    """What a verifier is allowed to accept, and the key material it accepts it with.

    ``audience`` binds the assertion to this deployment, and it is the one field with no default
    because an unset audience means every service holding the same key could use the same assertion.
    ``secret`` and ``jwks`` are read from the environment or passed in; a ``repr`` cannot leak either,
    and :attr:`safe_source` is what a log line should name instead.
    """

    audience: str
    issuer: str = ""
    secret: str = field(default="", repr=False)
    """Never rendered. What verifies an HS256, HS384, or HS512 assertion, and what a hidden repr and
    :attr:`safe_source` both exist to keep out of a log line."""

    jwks: Mapping[str, object] = field(default_factory=dict[str, object], repr=False)
    """The JWK Set document an RS256 or ES256 assertion is verified against, as JSON decodes it:
    ``{"keys": [...]}``. A document, not a URL — fetching one belongs to the deployment, and nothing
    in this package opens a socket."""

    algorithms: tuple[str, ...] = ()
    """The algorithms accepted. Empty, which is the default, means the family the key material
    implies: HS256/HS384/HS512 for a shared secret, RS256/ES256 for a JWKS."""

    leeway: float = 0.0
    """Seconds of clock skew tolerated on ``exp`` and ``nbf``. Zero by default: a positive value is a
    decision to accept an assertion that has just expired."""

    def __post_init__(self) -> None:
        if not self.audience:
            raise ConfigurationError(
                f"audience must not be empty: set {ENV_AUDIENCE}, because an assertion that names no "
                "audience is replayable against every service that shares the key"
            )
        if self.secret and self.jwks:
            raise ConfigurationError(
                "secret and jwks are mutually exclusive: accepting both lets an assertion's own "
                "header decide which key verifies it"
            )
        if not self.secret and not self.jwks:
            raise ConfigurationError(
                f"no key material: set {ENV_SECRET} for a shared secret, or {ENV_JWKS} for a JWKS "
                "document"
            )
        if self.leeway < 0:
            raise ConfigurationError("leeway must not be negative")
        algorithms = self._accepted_algorithms()
        object.__setattr__(self, "algorithms", algorithms)
        if self.jwks:
            try:
                document = normalize_jwks(self.jwks)
            except ValueError as error:
                raise ConfigurationError(f"the JWKS document cannot be used: {error}") from error
            object.__setattr__(self, "jwks", document)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> AuthSettings:
        """Build settings from ``XYBEROS_AUTH_*``, or from ``os.environ`` when no mapping is given.

        The environment is one of the two ways key material arrives, and the reason it is offered at
        all is that it is not a file: nothing here reads ``xyberos.toml``. ``XYBEROS_AUTH_SECRET`` and
        ``XYBEROS_AUTH_JWKS`` are alternatives to each other, and setting both is refused.
        """
        values = os.environ if environ is None else environ
        return cls(
            audience=values.get(ENV_AUDIENCE, ""),
            issuer=values.get(ENV_ISSUER, ""),
            secret=values.get(ENV_SECRET, ""),
            jwks=_jwks_from(values.get(ENV_JWKS, "")),
            algorithms=_algorithms_from(values.get(ENV_ALGORITHMS, "")),
            leeway=_leeway_from(values.get(ENV_LEEWAY, "")),
        )

    @property
    def safe_source(self) -> str:
        """Where the key material came from, for a log line. Never the material itself.

        A deployment that wants to record what it is verifying with records this, so the log says
        "shared secret (HS256)" or which key ids a JWKS offered, and never a value.
        """
        algorithms = ", ".join(self.algorithms)
        if self.secret:
            return f"shared secret ({algorithms})"
        key_ids = ", ".join(_key_ids(self.jwks))
        return f"JWKS ({algorithms}) with key ids: {key_ids or 'none'}"

    def _accepted_algorithms(self) -> tuple[str, ...]:
        """The accepted algorithms, refused here if they cannot be satisfied by the key material."""
        if self.algorithms:
            algorithms = tuple(dict.fromkeys(self.algorithms))
            unknown = [name for name in algorithms if name not in SUPPORTED_ALGORITHMS]
            if unknown:
                named = ", ".join(repr(name) for name in unknown)
                supported = ", ".join(SUPPORTED_ALGORITHMS)
                raise ConfigurationError(
                    f"unsupported algorithm(s) {named}; expected one of: {supported}"
                )
        else:
            algorithms = SHARED_SECRET_ALGORITHMS if self.secret else ASYMMETRIC_ALGORITHMS
        if self.secret and any(name not in SHARED_SECRET_ALGORITHMS for name in algorithms):
            named = ", ".join(SHARED_SECRET_ALGORITHMS)
            raise ConfigurationError(f"a shared secret can only verify {named}")
        if self.jwks and any(name not in ASYMMETRIC_ALGORITHMS for name in algorithms):
            named = ", ".join(ASYMMETRIC_ALGORITHMS)
            raise ConfigurationError(f"a JWKS can only verify {named}")
        return algorithms


def _algorithms_from(raw: str) -> tuple[str, ...]:
    """A comma-separated list of algorithm names, as the environment carries one."""
    return tuple(name.strip() for name in raw.split(",") if name.strip())


def _leeway_from(raw: str) -> float:
    """Seconds, as the environment carries them. The value is not echoed when it is not a number."""
    if not raw.strip():
        return 0.0
    try:
        return float(raw)
    except ValueError as error:
        raise ConfigurationError(f"{ENV_LEEWAY} must be a number of seconds") from error


def _jwks_from(raw: str) -> Mapping[str, object]:
    """A JWK Set document, as the environment carries one. The value is never echoed."""
    if not raw.strip():
        return {}
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ConfigurationError(f"{ENV_JWKS} is not JSON") from error
    if not isinstance(document, dict):
        raise ConfigurationError(f"{ENV_JWKS} is not a JSON object")
    return cast("dict[str, object]", document)


def _key_ids(document: Mapping[str, object]) -> tuple[str, ...]:
    """The key ids a JWKS document offers. Identifiers, not key material: they belong in a log."""
    keys = document.get("keys")
    if not isinstance(keys, tuple):
        return ()
    identifiers: list[str] = []
    for entry in cast("tuple[Mapping[str, object], ...]", keys):
        kid = entry.get("kid")
        if isinstance(kid, str) and kid:
            identifiers.append(kid)
    return tuple(identifiers)
