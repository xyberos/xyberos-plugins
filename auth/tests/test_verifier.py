"""What a shared secret verifies, and the refusals that are the evidence.

The tests are ordinary pytest tests: synchronous throughout, because verification is synchronous —
there is no ``pytest-asyncio`` here and nothing to await. Every assertion in this file is minted here
with ``hmac`` and ``hashlib`` rather than by the package, so a verifier that accepted its own encoding
would still fail these. Nothing here needs a network, a server, or a second process.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from xyberos.errors import ConfigurationError, HttpError, RequestValidationError

from xyberos_auth import AuthSettings, Principal, PrincipalVerifier
from xyberos_auth.settings import (
    ENV_ALGORITHMS,
    ENV_AUDIENCE,
    ENV_ISSUER,
    ENV_JWKS,
    ENV_LEEWAY,
    ENV_SECRET,
)

SECRET = "a-shared-secret-nobody-commits"
AUDIENCE = "checkout"
ISSUER = "https://issuer.example"
TENANT = "acme"

_DIGESTS = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}

#: A document that is well-formed enough to reach the "mutually exclusive" check.
MINIMAL_JWKS: dict[str, object] = {
    "keys": [{"kty": "RSA", "kid": "primary", "n": "AQAB", "e": "AQAB"}]
}


def _segment(data: bytes) -> str:
    """Base64url without padding, the way a JWS carries a segment."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _claims(**overrides: object) -> dict[str, object]:
    """A claim set a correct verifier accepts, with room for exactly one thing to be wrong."""
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "ada",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "tenant": TENANT,
        "scope": "tickets:read tickets:write",
    }
    claims.update(overrides)
    return claims


def _segments(
    claims: Mapping[str, object],
    header: Mapping[str, object],
) -> tuple[str, str]:
    """The header and payload segments of an assertion, encoded but not signed."""
    return (
        _segment(json.dumps(dict(header)).encode()),
        _segment(json.dumps(dict(claims)).encode()),
    )


def _assertion(
    claims: Mapping[str, object],
    *,
    secret: str = SECRET,
    algorithm: str = "HS256",
    header: Mapping[str, object] | None = None,
) -> str:
    """An assertion signed with ``secret``, built here rather than by the package."""
    head = {"alg": algorithm, "typ": "JWT"} if header is None else dict(header)
    header_segment, payload_segment = _segments(claims, head)
    signing_input = f"{header_segment}.{payload_segment}"
    signature = hmac.new(
        secret.encode(), signing_input.encode(), _DIGESTS[algorithm]
    ).digest()
    return f"{signing_input}.{_segment(signature)}"


def _settings(**overrides: object) -> AuthSettings:
    values: dict[str, object] = {"audience": AUDIENCE, "issuer": ISSUER, "secret": SECRET}
    values.update(overrides)
    return AuthSettings(**values)  # type: ignore[arg-type]


def _verifier(**overrides: object) -> PrincipalVerifier:
    return PrincipalVerifier(_settings(**overrides))


def test_a_genuine_assertion_becomes_a_principal() -> None:
    principal = _verifier().verify(_assertion(_claims()))

    assert principal.subject == "ada"
    assert principal.issuer == ISSUER
    assert principal.audiences == (AUDIENCE,)
    assert principal.scopes == ("tickets:read", "tickets:write")
    assert principal.claim("tenant") == TENANT
    assert principal.claim("nothing-like-this") is None
    assert principal.expires_at > datetime.now(tz=UTC)
    assert principal.issued_at is not None


def test_a_principal_is_a_value_that_cannot_be_mutated() -> None:
    verifier = _verifier()
    principal = verifier.verify(_assertion(_claims()))
    again = verifier.verify(_assertion(_claims()))

    assert principal == again, "the identity it verified decides equality"
    assert hash(principal) == hash(again)
    assert TENANT not in repr(principal), "claims are not part of a principal's repr"
    assert verifier.settings.audience == AUDIENCE
    with pytest.raises(FrozenInstanceError):
        principal.subject = "linus"  # type: ignore[misc]


def test_an_unsigned_assertion_is_refused() -> None:
    """The header claims an algorithm, and the signature is one nobody produced."""
    header_segment, payload_segment = _segments(_claims(), {"alg": "none", "typ": "JWT"})
    unsigned = f"{header_segment}.{payload_segment}.{_segment(b'nothing signed this')}"

    with pytest.raises(RequestValidationError, match="alg 'none', which is never accepted") as caught:
        _verifier().verify(unsigned)

    assert caught.value.status_code == 401


def test_an_assertion_with_no_signature_is_refused() -> None:
    header_segment, payload_segment = _segments(_claims(), {"alg": "HS256", "typ": "JWT"})

    for truncated in (f"{header_segment}.{payload_segment}", f"{header_segment}.{payload_segment}."):
        with pytest.raises(RequestValidationError, match="it carries no signature"):
            _verifier().verify(truncated)


def test_an_expired_assertion_is_refused() -> None:
    expired = _assertion(_claims(exp=int(time.time()) - 1))

    with pytest.raises(RequestValidationError, match="it expired at") as caught:
        _verifier().verify(expired)

    assert caught.value.status_code == 401


def test_an_assertion_for_another_audience_is_refused() -> None:
    """An assertion minted for another service must not be usable here."""
    for other in ("another-service", ["another-service"], ["another-service", "a-third"]):
        with pytest.raises(RequestValidationError, match="its aud does not include 'checkout'"):
            _verifier().verify(_assertion(_claims(aud=other)))


def test_a_second_audience_in_a_list_is_accepted() -> None:
    principal = _verifier().verify(_assertion(_claims(aud=["another-service", AUDIENCE])))

    assert principal.audiences == ("another-service", AUDIENCE)


def test_a_signature_from_another_secret_is_refused() -> None:
    forged = _assertion(_claims(), secret="the-wrong-secret")

    with pytest.raises(RequestValidationError, match="does not match the shared secret"):
        _verifier().verify(forged)


def test_the_signature_is_checked_before_any_claim_is_read() -> None:
    """A forged assertion is refused as forged, not as expired: claims are not trusted first."""
    forged = _assertion(_claims(exp=int(time.time()) - 1), secret="the-wrong-secret")

    with pytest.raises(RequestValidationError, match="does not match the shared secret"):
        _verifier().verify(forged)


def test_an_assertion_with_no_expiry_is_refused() -> None:
    claims = _claims()
    del claims["exp"]

    with pytest.raises(RequestValidationError, match="no 'exp' claim"):
        _verifier().verify(_assertion(claims))


def test_an_assertion_that_is_not_valid_yet_is_refused() -> None:
    with pytest.raises(RequestValidationError, match="it is not valid before"):
        _verifier().verify(_assertion(_claims(nbf=int(time.time()) + 60)))


def test_leeway_admits_a_clock_that_is_only_just_behind() -> None:
    expired = _assertion(_claims(exp=int(time.time()) - 5))

    assert _verifier(leeway=30.0).verify(expired).subject == "ada"
    with pytest.raises(RequestValidationError, match="it expired at"):
        _verifier().verify(expired)


def test_another_issuer_is_refused_and_an_unset_one_is_not_checked() -> None:
    elsewhere = _assertion(_claims(iss="https://somebody-else.example"))

    with pytest.raises(RequestValidationError, match="its iss is not"):
        _verifier().verify(elsewhere)
    assert _verifier(issuer="").verify(elsewhere).issuer == "https://somebody-else.example"


def test_an_assertion_without_a_subject_is_refused() -> None:
    for claims in (_claims(sub=""), _claims(sub=42), _claims(sub=None)):
        with pytest.raises(RequestValidationError, match="no 'sub' claim"):
            _verifier().verify(_assertion(claims))


def test_a_claim_that_is_not_a_time_is_refused() -> None:
    with pytest.raises(RequestValidationError, match="its 'exp' claim is not a number"):
        _verifier().verify(_assertion(_claims(exp="soon")))


@pytest.mark.parametrize(
    "assertion",
    ["", "one-segment-only", "a.b.c.d", "not base64!.also not.base64!"],
)
def test_a_malformed_assertion_is_refused(assertion: str) -> None:
    with pytest.raises(RequestValidationError) as caught:
        _verifier().verify(assertion)

    assert caught.value.status_code == 401


def test_a_segment_that_is_not_a_json_object_is_refused() -> None:
    header_segment, _ = _segments(_claims(), {"alg": "HS256"})
    not_an_object = _segment(b"[1, 2, 3]")
    not_json = _segment(b"this is not JSON")

    with pytest.raises(RequestValidationError, match="its header is not a JSON object"):
        _verifier().verify(f"{not_an_object}.{header_segment}.{_segment(b's')}")
    with pytest.raises(RequestValidationError, match="its payload is not base64url-encoded JSON"):
        _verifier().verify(f"{header_segment}.{not_json}.{_segment(b's')}")


def test_the_algorithm_must_be_one_the_settings_accept() -> None:
    stronger = _assertion(_claims(), algorithm="HS512")

    assert _verifier().verify(stronger).subject == "ada", "every HMAC SHA-2 size is accepted"
    assert _verifier(algorithms=("HS512",)).verify(stronger).subject == "ada"
    with pytest.raises(RequestValidationError, match="is not one this verifier accepts"):
        _verifier(algorithms=("HS256",)).verify(stronger)


def test_an_algorithm_named_twice_is_one_algorithm() -> None:
    assert _settings(algorithms=("HS512", "HS512")).algorithms == ("HS512",)


def test_a_refusal_is_a_401_that_an_adapter_can_expose() -> None:
    token = _assertion(_claims(), secret="the-wrong-secret")

    with pytest.raises(RequestValidationError) as caught:
        _verifier().verify(token)

    error = caught.value
    assert isinstance(error, HttpError), "a refusal is safe to expose to the caller"
    assert error.status_code == 401
    assert token not in str(error), "a refusal must never quote the assertion it refused"
    assert SECRET not in str(error)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"audience": ""}, "audience must not be empty"),
        ({"secret": "", "jwks": {}}, "no key material"),
        ({"jwks": MINIMAL_JWKS}, "secret and jwks are mutually exclusive"),
        ({"algorithms": ("RS256",)}, "a shared secret can only verify HS256, HS384, HS512"),
        ({"algorithms": ("PS256",)}, "unsupported algorithm"),
        ({"leeway": -1.0}, "leeway must not be negative"),
    ],
)
def test_settings_refuse_a_configuration_that_cannot_verify(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        _settings(**changes)


def test_settings_are_frozen() -> None:
    settings = _settings()

    with pytest.raises(FrozenInstanceError):
        settings.audience = "another-service"  # type: ignore[misc]


def test_the_secret_never_reaches_a_repr_or_a_log_line() -> None:
    """A repr is the quickest way for a credential to reach a log."""
    settings = _settings()

    assert SECRET not in repr(settings)
    assert SECRET not in settings.safe_source
    assert AUDIENCE in repr(settings), "a repr still says what is being verified"
    assert settings.safe_source == "shared secret (HS256, HS384, HS512)"


def test_settings_arrive_from_the_environment() -> None:
    settings = AuthSettings.from_environment(
        {
            ENV_AUDIENCE: AUDIENCE,
            ENV_ISSUER: ISSUER,
            ENV_SECRET: SECRET,
            ENV_ALGORITHMS: "HS512, HS384",
            ENV_LEEWAY: "30",
        }
    )

    assert settings.audience == AUDIENCE
    assert settings.issuer == ISSUER
    assert settings.algorithms == ("HS512", "HS384")
    assert settings.leeway == 30.0
    assert PrincipalVerifier(settings).verify(
        _assertion(_claims(), algorithm="HS512")
    ).subject == "ada"


def test_the_process_environment_is_the_default_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_AUDIENCE, AUDIENCE)
    monkeypatch.setenv(ENV_SECRET, SECRET)
    monkeypatch.delenv(ENV_JWKS, raising=False)

    settings = AuthSettings.from_environment()

    assert settings.secret == SECRET
    assert settings.jwks == {}


def test_the_environment_refuses_a_value_it_cannot_read() -> None:
    with pytest.raises(ConfigurationError, match=f"{ENV_LEEWAY} must be a number of seconds"):
        AuthSettings.from_environment(
            {ENV_AUDIENCE: AUDIENCE, ENV_SECRET: SECRET, ENV_LEEWAY: "soon"}
        )
    with pytest.raises(ConfigurationError, match=f"{ENV_JWKS} is not JSON"):
        AuthSettings.from_environment({ENV_AUDIENCE: AUDIENCE, ENV_JWKS: "{oops"})
    with pytest.raises(ConfigurationError, match="audience must not be empty"):
        AuthSettings.from_environment({ENV_SECRET: SECRET})


def test_the_environment_names_the_variables_a_deployment_must_set() -> None:
    with pytest.raises(ConfigurationError, match=ENV_SECRET):
        AuthSettings.from_environment({ENV_AUDIENCE: AUDIENCE})


def test_a_principal_can_be_faked_for_a_test_without_the_verifier() -> None:
    """`app.with_overrides` needs a principal it can build, and this is what one looks like."""
    principal = Principal(subject="ada", expires_at=datetime.now(tz=UTC), claims={"tenant": TENANT})

    assert principal.claim("tenant") == TENANT
    assert principal.scopes == ()
