"""Verification only: an assertion in, a ``Principal`` or a refusal out.

An assertion arrives from a caller — a signed JWT that a proxy, an ingress, or an identity provider
minted — and this package answers one question: is it genuine? It checks the signature against a
shared secret or a JWKS, checks that the assertion is in time and is for this audience, and returns
the principal it establishes:

    from xyberos.errors import RequestValidationError
    from xyberos_auth import AuthSettings, PrincipalVerifier

    verifier = PrincipalVerifier(AuthSettings.from_environment())
    principal = verifier.verify(request.headers["authorization"].removeprefix("Bearer "))

The package registers nothing: no provider, no plugin entry point, no middleware, and no
configuration file of its own — key material comes from an explicit settings object or from
``XYBEROS_AUTH_*``. ADR 0014 owns the other half, so an application decides what a principal means and
what it may do, and this package never decides it for them.

The OAuth2 flows, the OIDC discovery machinery, and the Auth0/Okta/Entra presets that the published
``0.1.2`` bundled are not here and do not return.
"""

from xyberos_auth.settings import AuthSettings
from xyberos_auth.verifier import Principal, PrincipalVerifier

__all__ = ["AuthSettings", "Principal", "PrincipalVerifier"]
