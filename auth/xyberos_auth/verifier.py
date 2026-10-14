"""Turn an assertion into a ``Principal``, or refuse. Nothing else.

The refusals are the evidence. An unsigned assertion, an expired one, and one minted for another
audience are each refused with the framework's own error type — ``RequestValidationError``, which
derives from ``HttpError`` and therefore carries the ``401`` an adapter uses and a message the error
policy is willing to expose. Nothing in a refusal quotes the assertion, because a refusal that echoes
the token it rejected has put a credential in a log.

What this module deliberately does not do is decide what a principal may do. There are no roles, no
scopes check, no session, and no tenancy model here:
[ADR 0014](https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0014-no-identity-or-authorization-model.md)
owns that half, so this package establishes the assertion and the application decides what it means.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from xyberos.errors import ConfigurationError, RequestValidationError

from xyberos_auth.jwt import (
    decode_json_object,
    decode_segment,
    hmac_matches,
    load_public_keys,
    split_assertion,
    verify_signature,
)
from xyberos_auth.settings import AuthSettings

if TYPE_CHECKING:
    from xyberos_auth.jwt import KeyId, PublicKey

#: The status a refused assertion carries. It is the status the tenancy example uses for the same
#: condition, and the reason a refusal is a refusal rather than a crash.
UNAUTHENTICATED_STATUS: Final = 401


@dataclass(frozen=True)
class Principal:
    """Who an assertion says is calling, and what the verifier established about them.

    A value, not a session: it is what a service should take as an argument. ``claims`` carries the
    assertion's own claims so an application can interpret the ones this package does not — a tenant,
    an email, a role list — but it is left out of ``repr`` and of equality, because a principal is
    the identity it verified and not the payload it arrived in.
    """

    subject: str
    expires_at: datetime
    issuer: str | None = None
    audiences: tuple[str, ...] = ()
    issued_at: datetime | None = None
    scopes: tuple[str, ...] = ()
    claims: Mapping[str, object] = field(
        default_factory=dict[str, object], compare=False, repr=False
    )

    def claim(self, name: str) -> object | None:
        """A claim this package does not interpret — ``tenant``, ``email`` — or ``None``.

        Reading a claim is not authorizing anything: the value is what the issuer said, and what it
        entitles the caller to is the application's decision.
        """
        return self.claims.get(name)


class PrincipalVerifier:
    """Answers one question about an assertion — is it genuine? — and stops.

    It is constructed explicitly and registered by nobody: this package calls no ``app.provide``,
    installs no middleware, and declares no entry point, so a deployment that never builds a verifier
    has no authentication at all and nothing here will warn it (ADR 0014). A verifier built from a
    JWKS loads ``cryptography`` in its constructor; one built from a shared secret never loads it.
    """

    def __init__(self, settings: AuthSettings) -> None:
        self._settings = settings
        self._secret = settings.secret.encode()
        self._keys: tuple[tuple[KeyId, PublicKey], ...] = (
            _load_keys(settings) if settings.jwks else ()
        )

    @property
    def settings(self) -> AuthSettings:
        """The settings this verifier was built with. A log line names ``settings.safe_source``."""
        return self._settings

    def verify(self, assertion: str) -> Principal:
        """Return the verified principal for an assertion, or raise a refusal.

        The signature is checked before any claim is read, because a claim in an unverified assertion
        is a claim by whoever wrote it. After that the assertion must be in time, must name this
        deployment in ``aud``, must match the configured ``iss`` when one is configured, and must
        carry a ``sub``; anything else is a ``RequestValidationError`` at status ``401``.
        """
        header, claims, signature, signing_input = _decode(assertion)
        algorithm = self._algorithm(header)
        self._check_signature(header, algorithm, signing_input, signature)
        expires_at = _expiry(claims)
        self._check_times(claims, expires_at)
        self._check_issuer(claims)
        audiences = _string_list(claims.get("aud"), "aud")
        if self._settings.audience not in audiences:
            raise _refuse(f"its aud does not include {self._settings.audience!r}")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise _refuse("it carries no 'sub' claim")
        issuer = claims.get("iss")
        return Principal(
            subject=subject,
            expires_at=expires_at,
            issuer=issuer if isinstance(issuer, str) and issuer else None,
            audiences=audiences,
            issued_at=_timestamp(claims, "iat"),
            scopes=tuple(
                scope for entry in _string_list(claims.get("scope"), "scope") for scope in entry.split()
            ),
            claims=MappingProxyType(dict(claims)),
        )

    def _algorithm(self, header: Mapping[str, object]) -> str:
        """The assertion's algorithm, refused unless the settings accept it — and never ``none``."""
        algorithm = header.get("alg")
        if not isinstance(algorithm, str) or not algorithm:
            raise _refuse("its header declares no alg")
        if algorithm.lower() == "none":
            raise _refuse("its header declares alg 'none', which is never accepted")
        if algorithm not in self._settings.algorithms:
            accepted = ", ".join(self._settings.algorithms)
            raise _refuse(f"alg {algorithm!r} is not one this verifier accepts ({accepted})")
        return algorithm

    def _check_signature(
        self,
        header: Mapping[str, object],
        algorithm: str,
        signing_input: bytes,
        signature: bytes,
    ) -> None:
        """Refuse a signature that is not the configured key material's, or not that key's at all."""
        if self._secret:
            if not hmac_matches(self._secret, algorithm, signing_input, signature):
                raise _refuse("its signature does not match the shared secret")
            return
        kid, key = self._select_key(header)
        try:
            matched = verify_signature(key, algorithm, signing_input, signature)
        except ValueError as error:
            raise _refuse(str(error)) from error
        if not matched:
            named = f"kid {kid!r}" if kid else "the configured key"
            raise _refuse(f"its signature does not match {named}")

    def _select_key(self, header: Mapping[str, object]) -> tuple[KeyId, PublicKey]:
        """The key the assertion names, or the only key there is when it names none."""
        kid = header.get("kid")
        if kid is not None and not isinstance(kid, str):
            raise _refuse("its header carries a kid that is not a string")
        if not kid:
            if len(self._keys) != 1:
                raise _refuse(f"its header names no kid and the JWKS has {len(self._keys)} keys")
            return self._keys[0]
        for known, key in self._keys:
            if known == kid:
                return known, key
        raise _refuse(f"the JWKS has no key with kid {kid!r}")

    def _check_times(self, claims: Mapping[str, object], expires_at: datetime) -> None:
        """Refuse an assertion that has expired, or that is not valid yet, beyond the leeway."""
        now = datetime.now(tz=UTC)
        leeway = timedelta(seconds=self._settings.leeway)
        if expires_at + leeway < now:
            raise _refuse(f"it expired at {expires_at.isoformat()}")
        not_before = _timestamp(claims, "nbf")
        if not_before is not None and not_before - leeway > now:
            raise _refuse(f"it is not valid before {not_before.isoformat()}")

    def _check_issuer(self, claims: Mapping[str, object]) -> None:
        """Refuse an assertion minted by another issuer, when the settings name one."""
        expected = self._settings.issuer
        if expected and claims.get("iss") != expected:
            raise _refuse(f"its iss is not {expected!r}")


def _load_keys(settings: AuthSettings) -> tuple[tuple[KeyId, PublicKey], ...]:
    """Build the JWKS public keys, reporting a document or an install that cannot be used.

    ``cryptography`` is imported here, so a deployment that verifies with a shared secret does not
    need it loaded. A missing one is a broken install rather than a rejected caller, which is why it
    is a ``ConfigurationError`` raised at construction instead of a ``500`` on the first request.
    """
    try:
        return load_public_keys(settings.jwks)
    except ImportError as error:
        raise ConfigurationError(
            "verifying against a JWKS needs the 'cryptography' package, which xyberos-auth declares"
        ) from error
    except ValueError as error:
        raise ConfigurationError(f"the JWKS document cannot be used: {error}") from error


def _decode(assertion: str) -> tuple[dict[str, object], dict[str, object], bytes, bytes]:
    """Split and decode an assertion, refusing anything that is not three base64url segments."""
    try:
        header_segment, claims_segment, signature_segment = split_assertion(assertion)
        header = decode_json_object(header_segment, name="header")
        claims = decode_json_object(claims_segment, name="payload")
        signature = decode_segment(signature_segment, name="signature")
    except ValueError as error:
        raise _refuse(str(error)) from error
    if not signature:
        raise _refuse("it carries no signature")
    return header, claims, signature, f"{header_segment}.{claims_segment}".encode("ascii")


def _expiry(claims: Mapping[str, object]) -> datetime:
    """The ``exp`` claim, which is required: an assertion with no expiry is an unbounded one."""
    expires_at = _timestamp(claims, "exp")
    if expires_at is None:
        raise _refuse("it carries no 'exp' claim; an assertion with no expiry is unbounded")
    return expires_at


def _timestamp(claims: Mapping[str, object], name: str) -> datetime | None:
    """A NumericDate claim as an aware UTC datetime, or ``None`` when the claim is absent."""
    value = claims.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _refuse(f"its {name!r} claim is not a number")
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OSError, OverflowError, ValueError) as error:
        raise _refuse(f"its {name!r} claim is not a time this system can represent") from error


def _string_list(value: object, name: str) -> tuple[str, ...]:
    """A claim JWS lets be one string or a list of them, as a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        items: list[str] = []
        for item in cast("list[object]", value):
            if not isinstance(item, str):
                raise _refuse(f"its {name!r} claim mixes strings with something else")
            items.append(item)
        return tuple(items)
    raise _refuse(f"its {name!r} claim is neither a string nor a list of strings")


def _refuse(reason: str) -> RequestValidationError:
    """A refusal: a ``401`` whose message names the check and never quotes the assertion.

    ``RequestValidationError`` derives from ``HttpError``, so the framework's own error policy
    exposes the message to the caller and an adapter answers with its status. The framework's type is
    used rather than a new one on purpose: a second unauthenticated-error type in the ecosystem would
    be a second thing for an error policy to know about.
    """
    return RequestValidationError(
        f"the request is not authenticated: {reason}",
        status_code=UNAUTHENTICATED_STATUS,
    )
