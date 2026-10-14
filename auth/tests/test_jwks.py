"""The asymmetric path, and the import it is allowed to need — and only when it is needed.

An RS256 or ES256 assertion is verified against a JWK Set *document*, not a URL: this package opens no
socket, and fetching a JWKS belongs to the deployment that already owns its trust configuration. The
keys are generated here and the assertions are signed here with ``cryptography`` rather than by the
package, so a verifier that accepted its own encoding would fail these.

The last test is the promise the module docstring makes: a deployment that verifies with a shared
secret needs nothing extra. It is checked in a fresh interpreter, where ``cryptography`` cannot
already be loaded by another test.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from xyberos.errors import ConfigurationError, RequestValidationError

from xyberos_auth import AuthSettings, PrincipalVerifier

AUDIENCE = "checkout"
ISSUER = "https://issuer.example"

#: Generated once: RSA key generation is the slowest thing in this file, and a key is immutable.
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EC_KEY = ec.generate_private_key(ec.SECP256R1())


def _segment(data: bytes) -> str:
    """Base64url without padding, the way a JWS carries a segment."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _integer(value: int) -> str:
    """A JWK numeric member: base64url big-endian, not decimal."""
    return _segment(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def _rsa_jwk(kid: str | None, key: rsa.RSAPrivateKey = RSA_KEY) -> dict[str, object]:
    """The public JWK of an RSA key, as an issuer would publish it."""
    numbers = key.public_key().public_numbers()
    return {"kty": "RSA", "kid": kid, "n": _integer(numbers.n), "e": _integer(numbers.e)}


def _ec_jwk(kid: str | None, key: ec.EllipticCurvePrivateKey = EC_KEY) -> dict[str, object]:
    """The public JWK of a P-256 key, which is the curve ES256 names."""
    numbers = key.public_key().public_numbers()
    return {
        "kty": "EC",
        "kid": kid,
        "crv": "P-256",
        "x": _integer(numbers.x),
        "y": _integer(numbers.y),
    }


def _jwks(*keys: dict[str, object]) -> dict[str, object]:
    return {"keys": list(keys)}


def _claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": "ada",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "tenant": "acme",
    }
    claims.update(overrides)
    return claims


def _header(algorithm: str, kid: str | None) -> dict[str, object]:
    header: dict[str, object] = {"alg": algorithm, "typ": "JWT"}
    if kid is not None:
        header["kid"] = kid
    return header


def _signing_input(
    claims: Mapping[str, object],
    algorithm: str,
    kid: str | None,
) -> str:
    return ".".join(
        (
            _segment(json.dumps(_header(algorithm, kid)).encode()),
            _segment(json.dumps(dict(claims)).encode()),
        )
    )


def _rs256(
    claims: Mapping[str, object],
    *,
    kid: str | None = "primary",
    key: rsa.RSAPrivateKey = RSA_KEY,
) -> str:
    """An RS256 assertion, signed here rather than by the package under test."""
    signing_input = _signing_input(claims, "RS256", kid)
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_segment(signature)}"


def _es256(
    claims: Mapping[str, object],
    *,
    kid: str | None = "primary",
    key: ec.EllipticCurvePrivateKey = EC_KEY,
) -> str:
    """An ES256 assertion: the raw two-half signature JWS specifies, not DER."""
    signing_input = _signing_input(claims, "ES256", kid)
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{signing_input}.{_segment(raw)}"


def _unsupported_algorithm(claims: Mapping[str, object], algorithm: str) -> str:
    """An assertion whose header names an algorithm the settings cannot use."""
    signing_input = _signing_input(claims, algorithm, None)
    return f"{signing_input}.{_segment(b'nothing worth reading')}"


def _verifier(*keys: dict[str, object], algorithms: tuple[str, ...] = ()) -> PrincipalVerifier:
    return PrincipalVerifier(
        AuthSettings(
            audience=AUDIENCE,
            issuer=ISSUER,
            jwks=_jwks(*keys),
            algorithms=algorithms,
        )
    )


def test_an_rs256_assertion_verifies_against_a_jwks() -> None:
    verifier = _verifier(_rsa_jwk("primary"))

    principal = verifier.verify(_rs256(_claims()))

    assert principal.subject == "ada"
    assert principal.issuer == ISSUER
    assert principal.audiences == (AUDIENCE,)


def test_an_es256_assertion_verifies_against_a_jwks() -> None:
    verifier = _verifier(_ec_jwk("primary"))

    assert verifier.verify(_es256(_claims())).subject == "ada"


def test_a_jwks_with_one_key_needs_no_key_id_in_the_assertion() -> None:
    verifier = _verifier(_rsa_jwk(None))

    assert verifier.verify(_rs256(_claims(), kid=None)).subject == "ada"


def test_a_key_id_is_required_when_the_jwks_offers_more_than_one_key() -> None:
    verifier = _verifier(_rsa_jwk("primary"), _ec_jwk("backup"))

    with pytest.raises(RequestValidationError, match="names no kid and the JWKS has 2 keys"):
        verifier.verify(_rs256(_claims(), kid=None))


def test_an_unknown_key_id_is_refused() -> None:
    verifier = _verifier(_rsa_jwk("primary"))

    with pytest.raises(RequestValidationError, match="the JWKS has no key with kid 'retired'") as caught:
        verifier.verify(_rs256(_claims(), kid="retired"))

    assert caught.value.status_code == 401


def test_an_assertion_signed_by_another_key_is_refused() -> None:
    verifier = _verifier(_rsa_jwk("primary"))

    with pytest.raises(RequestValidationError, match="does not match kid 'primary'"):
        verifier.verify(_rs256(_claims(), key=OTHER_RSA_KEY))


def test_a_shared_secret_assertion_is_refused_by_a_jwks_verifier() -> None:
    """The confusion this package will not have: an HMAC signature "verified" with a public key."""
    verifier = _verifier(_rsa_jwk("primary"))

    with pytest.raises(RequestValidationError, match="is not one this verifier accepts"):
        verifier.verify(_unsupported_algorithm(_claims(), "HS256"))


def test_a_key_of_the_wrong_type_is_refused() -> None:
    verifier = _verifier(_rsa_jwk("primary"), algorithms=("ES256",))

    with pytest.raises(RequestValidationError, match="its key does not match alg ES256"):
        verifier.verify(_es256(_claims()))


def test_an_algorithm_the_settings_do_not_allow_is_refused() -> None:
    verifier = _verifier(_rsa_jwk("primary"), algorithms=("RS256",))

    with pytest.raises(RequestValidationError, match="is not one this verifier accepts"):
        verifier.verify(_es256(_claims()))


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"keys": "not-a-list"}, "it has no 'keys' list"),
        ({"keys": []}, "its 'keys' list is empty"),
        ({"keys": ["not-a-key"]}, "key #0 is not a JWK object"),
        ({"keys": [{"kty": "oct", "k": "AQAB"}]}, "unsupported kty"),
        ({"keys": [{"kty": "RSA", "n": "AQAB"}]}, "has no 'e' member"),
        ({"keys": [{"kty": "RSA", "n": "not base64!", "e": "AQAB"}]}, "not base64url"),
        ({"keys": [{"kty": "EC", "crv": "P-384", "x": "AQAB", "y": "AQAB"}]}, "not on curve P-256"),
        ({"keys": [{"kty": "RSA", "kid": 7, "n": "AQAB", "e": "AQAB"}]}, "kid that is not a string"),
        (
            {
                "keys": [
                    {"kty": "RSA", "kid": "primary", "n": "AQAB", "e": "AQAB"},
                    {"kty": "RSA", "kid": "primary", "n": "AQAB", "e": "AQAB"},
                ]
            },
            "two keys share the kid",
        ),
    ],
)
def test_a_jwks_a_deployment_could_not_verify_with_is_refused(
    document: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        AuthSettings(audience=AUDIENCE, jwks=document)


def test_the_jwks_document_cannot_be_changed_after_the_settings_are_built() -> None:
    document = _jwks(_rsa_jwk("primary"))
    verifier = PrincipalVerifier(AuthSettings(audience=AUDIENCE, jwks=document))

    cast("list[object]", document["keys"]).append(_ec_jwk("sneaky"))

    keys = verifier.settings.jwks["keys"]
    assert isinstance(keys, tuple)
    assert len(keys) == 1, "the settings kept their own copy"
    assert verifier.verify(_rs256(_claims(), kid=None)).subject == "ada"
    with pytest.raises(RequestValidationError, match="no key with kid 'sneaky'"):
        verifier.verify(_rs256(_claims(), kid="sneaky"))


def test_the_safe_source_names_the_key_ids_without_the_material() -> None:
    settings = AuthSettings(audience=AUDIENCE, jwks=_jwks(_rsa_jwk("primary"), _ec_jwk("backup")))

    assert settings.safe_source == "JWKS (RS256, ES256) with key ids: primary, backup"
    assert _integer(RSA_KEY.public_key().public_numbers().n) not in settings.safe_source


def test_a_shared_secret_verifier_never_imports_cryptography() -> None:
    """Checked where it can actually be checked: a process that has loaded nothing else."""
    script = (
        "import base64, hashlib, hmac, json, sys, time\n"
        "from xyberos_auth import AuthSettings, PrincipalVerifier\n"
        "\n"
        "def encode(data: bytes) -> str:\n"
        "    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()\n"
        "\n"
        "claims = {'sub': 'ada', 'aud': 'checkout', 'exp': int(time.time()) + 300}\n"
        "header = encode(json.dumps({'alg': 'HS256'}).encode())\n"
        "payload = encode(json.dumps(claims).encode())\n"
        "signing_input = header + '.' + payload\n"
        "digest = hashlib.sha256\n"
        "signature = hmac.new(b'a-shared-secret', signing_input.encode(), digest).digest()\n"
        "verifier = PrincipalVerifier(AuthSettings(audience='checkout', secret='a-shared-secret'))\n"
        "assert verifier.verify(signing_input + '.' + encode(signature)).subject == 'ada'\n"
        "assert 'cryptography' not in sys.modules\n"
        "print('cryptography was never imported')\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "cryptography was never imported" in completed.stdout
