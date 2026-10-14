"""The mechanism of an assertion, and the one place ``cryptography`` is allowed to appear.

A JWS is three base64url segments, and verifying one is a small amount of arithmetic that the
standard library already provides for a shared secret: ``hmac`` compares in constant time and
``hashlib`` supplies the digest. An asymmetric signature is the only thing that needs a library, so
the import sits inside :func:`load_public_keys` and :func:`verify_signature` rather than at the top
of this module — a deployment that verifies with a shared secret never loads ``cryptography``, and
neither does importing ``xyberos_auth``.

Nothing here decides whether an assertion is *acceptable*: expiry, issuer, and audience belong to
:mod:`xyberos_auth.verifier`. What this module decides is whether a signature is genuine, and a
document it cannot read raises ``ValueError`` rather than a refusal, because a malformed JWKS is a
configuration mistake and not a rejected caller.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeAlias, cast

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

    #: A public key this package can verify with. Only ever built where ``cryptography`` is loaded.
    PublicKey: TypeAlias = RSAPublicKey | EllipticCurvePublicKey

#: A key id, as a JWK carries it. ``None`` when the issuer published one key and no ``kid``.
KeyId: TypeAlias = str | None

#: The algorithms a shared secret can produce: HMAC over SHA-2, which the standard library owns.
SHARED_SECRET_ALGORITHMS: tuple[str, ...] = ("HS256", "HS384", "HS512")

#: The algorithms a JWKS can verify. RS256 is RSA with PKCS#1 v1.5 and SHA-256; ES256 is ECDSA over
#: P-256 with SHA-256. Both are the pairings JWS specifies, so no hash is chosen per key here.
ASYMMETRIC_ALGORITHMS: tuple[str, ...] = ("RS256", "ES256")

SUPPORTED_ALGORITHMS: tuple[str, ...] = SHARED_SECRET_ALGORITHMS + ASYMMETRIC_ALGORITHMS

#: The curve ES256 is defined over. A P-384 key would be ES384, which this package does not claim.
_ES256_CURVE = "P-256"

#: ES256 signatures are the raw ``r || s`` pair — two 32-byte halves, not DER.
_ES256_SIGNATURE_BYTES = 64

_HMAC_DIGESTS: Mapping[str, str] = {
    "HS256": "sha256",
    "HS384": "sha384",
    "HS512": "sha512",
}


def split_assertion(assertion: str) -> tuple[str, str, str]:
    """Return the header, payload, and signature segments of an assertion.

    An absent signature is a refusal rather than a parse error, so fewer than three segments raise
    ``ValueError`` saying the assertion carries no signature: an unsigned assertion is the first
    thing an attacker tries, and the refusal should name it.
    """
    parts = assertion.split(".")
    if len(parts) < 3:
        raise ValueError("it carries no signature")
    if len(parts) > 3:
        raise ValueError("it has more than three dot-separated segments")
    return parts[0], parts[1], parts[2]


def decode_json_object(segment: str, *, name: str) -> dict[str, object]:
    """Decode one base64url segment into a JSON object, or report which segment failed."""
    try:
        decoded = json.loads(decode_segment(segment, name=name))
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(f"its {name} is not base64url-encoded JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"its {name} is not a JSON object")
    return cast("dict[str, object]", decoded)


def decode_segment(segment: str, *, name: str) -> bytes:
    """Decode one base64url segment, refusing anything outside the alphabet.

    ``validate=True`` matters: the default decoder discards characters it does not recognise, which
    would let a malformed segment decode to something plausible-looking.
    """
    try:
        encoded = segment.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError(f"its {name} is not base64url") from error
    padded = encoded + b"=" * (-len(encoded) % 4)
    try:
        return base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"its {name} is not base64url") from error


def hmac_matches(secret: bytes, algorithm: str, signing_input: bytes, signature: bytes) -> bool:
    """Whether ``signature`` is this secret's HMAC over the signing input.

    ``compare_digest`` is constant-time, so an attacker cannot learn the expected signature a byte at
    a time. An algorithm a shared secret cannot produce is a ``ValueError``: the verifier refuses it
    earlier, so reaching this with one would be a bug rather than a rejection.
    """
    digest = _HMAC_DIGESTS.get(algorithm)
    if digest is None:
        raise ValueError(f"{algorithm} is not an algorithm a shared secret can produce")
    expected = hmac.new(secret, signing_input, digest).digest()
    return hmac.compare_digest(expected, signature)


def normalize_jwks(document: Mapping[str, object]) -> Mapping[str, object]:
    """Validate a JWK Set document and return an immutable copy of it.

    The shape is checked here, where it is configuration and not request input: a document without a
    ``keys`` list, an empty one, a key whose ``kty`` is neither RSA nor an EC P-256 key, a duplicate
    ``kid``, and a member that is not base64url all fail loudly at composition time. None of it needs
    ``cryptography`` — reading ``n``, ``e``, ``x``, and ``y`` is integer arithmetic, and building a
    key object is :func:`load_public_keys`'s job.
    """
    keys = document.get("keys")
    if not isinstance(keys, (list, tuple)):
        raise ValueError("it has no 'keys' list")
    if not keys:
        raise ValueError("its 'keys' list is empty")
    entries: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for index, entry in enumerate(cast("Sequence[object]", keys)):
        if not isinstance(entry, Mapping):
            raise ValueError(f"key #{index} is not a JWK object")
        key = cast("Mapping[str, object]", entry)
        kid = key.get("kid")
        if kid is not None and not isinstance(kid, str):
            raise ValueError(f"key #{index} has a kid that is not a string")
        if isinstance(kid, str) and kid:
            if kid in seen:
                raise ValueError(f"two keys share the kid {kid!r}")
            seen.add(kid)
        entries.append(MappingProxyType(_validated_jwk(key, index=index)))
    return MappingProxyType({"keys": tuple(entries)})


def load_public_keys(document: Mapping[str, object]) -> tuple[tuple[KeyId, PublicKey], ...]:
    """Build the public keys of a JWKS document, importing ``cryptography`` now and only now."""
    # normalize_jwks owns the shape, so every entry below is a JWK whose members were checked.
    keys = cast("tuple[Mapping[str, object], ...]", normalize_jwks(document).get("keys"))
    resolved: list[tuple[KeyId, PublicKey]] = []
    for key in keys:
        kid = key.get("kid")
        resolved.append((kid if isinstance(kid, str) and kid else None, _public_key(key)))
    return tuple(resolved)


def verify_signature(
    key: PublicKey,
    algorithm: str,
    signing_input: bytes,
    signature: bytes,
) -> bool:
    """Whether ``signature`` is this key's signature over the signing input.

    A key that cannot produce this algorithm's signature raises ``ValueError`` rather than returning
    ``False``, because that is a mismatch between the assertion's header and the configured key
    material — a refusal the verifier words — and not a bad signature. An ES256 signature that is not
    two 32-byte halves is simply not a signature, so it is ``False``.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    try:
        if algorithm == "RS256":
            if not isinstance(key, rsa.RSAPublicKey):
                raise ValueError(f"its key does not match alg {algorithm}")
            key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
        elif algorithm == "ES256":
            if not isinstance(key, ec.EllipticCurvePublicKey):
                raise ValueError(f"its key does not match alg {algorithm}")
            if len(signature) != _ES256_SIGNATURE_BYTES:
                return False
            half = _ES256_SIGNATURE_BYTES // 2
            der = encode_dss_signature(
                int.from_bytes(signature[:half], "big"),
                int.from_bytes(signature[half:], "big"),
            )
            key.verify(der, signing_input, ec.ECDSA(hashes.SHA256()))
        else:
            raise ValueError(f"alg {algorithm} is not an asymmetric algorithm")
    except InvalidSignature:
        return False
    return True


def _validated_jwk(key: Mapping[str, object], *, index: int) -> dict[str, object]:
    """Check one JWK's members for its key type, so a broken document fails at composition."""
    kty = key.get("kty")
    if kty == "RSA":
        return {
            "kty": kty,
            "kid": key.get("kid"),
            "n": _base64_member(key, "n", index=index),
            "e": _base64_member(key, "e", index=index),
        }
    if kty == "EC":
        curve = key.get("crv")
        if curve != _ES256_CURVE:
            raise ValueError(f"key #{index} is not on curve {_ES256_CURVE}: {curve!r}")
        return {
            "kty": kty,
            "kid": key.get("kid"),
            "crv": curve,
            "x": _base64_member(key, "x", index=index),
            "y": _base64_member(key, "y", index=index),
        }
    raise ValueError(f"key #{index} has an unsupported kty: {kty!r}")


def _base64_member(key: Mapping[str, object], member: str, *, index: int) -> str:
    """Return one base64url member of a JWK, read far enough to know the key can be built."""
    value = key.get(member)
    if not isinstance(value, str) or not value:
        raise ValueError(f"key #{index} has no {member!r} member")
    try:
        decode_segment(value, name=f"key #{index} {member}")
    except ValueError as error:
        raise ValueError(f"key #{index} has a {member!r} member that is not base64url") from error
    return value


def _public_key(key: Mapping[str, object]) -> PublicKey:
    """Build one public key from a JWK that :func:`normalize_jwks` has already accepted."""
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    if key.get("kty") == "RSA":
        return rsa.RSAPublicNumbers(
            _integer_member(key, "e"),
            _integer_member(key, "n"),
        ).public_key()
    return ec.EllipticCurvePublicNumbers(
        _integer_member(key, "x"),
        _integer_member(key, "y"),
        ec.SECP256R1(),
    ).public_key()


def _integer_member(key: Mapping[str, object], member: str) -> int:
    """A JWK's numeric member, which is base64url big-endian rather than a JSON number."""
    return int.from_bytes(
        decode_segment(cast("str", key[member]), name=member),
        "big",
        signed=False,
    )
