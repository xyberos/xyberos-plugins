# xyberos-auth

**Verification only: an assertion arrives, this package answers whether it is genuine, and it stops.**

The OAuth2 flows, the OIDC discovery machinery, and the Auth0/Okta/Entra presets that the published
`0.1.2` bundled are **not** here, and they do not return. What returns is the half that belongs to a
framework's edge and nothing more: an assertion from a caller is verified against a shared secret
(HS256, HS384, HS512 — standard library only) or a JWKS (RS256, ES256), and the result is a
`Principal`. [ADR 0014](https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0014-no-identity-or-authorization-model.md)
owns the policy half, so this package never decides what a principal may do.

Nothing is registered either. There is no `app.provide` call, no plugin entry point, and no
middleware: a deployment that never builds a verifier has no authentication at all, and nothing here
will warn it. That is deliberate — a verifier is a component you construct, hand a principal to, and
its refusals are what make a header trusted rather than merely present.

## Install

```bash
pip install xyberos-auth
```

## Use it

```python
from xyberos import HttpError
from xyberos_auth import AuthSettings, PrincipalVerifier

verifier = PrincipalVerifier(AuthSettings.from_environment())

def principal_from(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HttpError("the request is not authenticated", status_code=401)
    return verifier.verify(authorization.removeprefix("Bearer "))
```

`verify` returns a `Principal` — `subject`, `issuer`, `audiences`, `expires_at`, `issued_at`,
`scopes`, and the assertion's own `claims` for anything the application decides — or raises
`xyberos.errors.RequestValidationError` with `status_code == 401`, whose message names the check it
failed and never quotes the assertion. Because that type derives from `HttpError`, the framework's
error policy is willing to expose it to the caller and the adapter answers with the status; this
package deliberately adds no second unauthenticated-error type to the ecosystem.

The shape to build on is the tenancy example in the core repository: pass the verified principal to
your service **as an argument**, scope your queries by what it carries, and strip any
client-supplied assertion header at the edge. A header that merely arrived proves nothing.

## Key material

Key material comes from an explicit `AuthSettings` object or from the environment. There is no
configuration file, because the one thing that must never be committed is the key:

| Variable | What it is |
| --- | --- |
| `XYBEROS_AUTH_AUDIENCE` | **Required.** The audience this deployment accepts. An assertion minted for another service must not be usable here. |
| `XYBEROS_AUTH_SECRET` | The shared secret for HS256/HS384/HS512. |
| `XYBEROS_AUTH_JWKS` | The JWK Set **document** as JSON — `{"keys": [...]}` — for RS256/ES256. |
| `XYBEROS_AUTH_ISSUER` | The `iss` to require, when one should be checked. |
| `XYBEROS_AUTH_ALGORITHMS` | A comma-separated allowlist. Empty means the family the key material implies. |
| `XYBEROS_AUTH_LEEWAY` | Seconds of clock skew tolerated on `exp` and `nbf`. Zero by default. |

Three of those decisions are refusals rather than defaults. An empty `audience` is refused at
construction, because an assertion no one checks the audience of is replayable against every service
sharing the key. A secret and a JWKS are mutually exclusive, because accepting both lets an
assertion's own header decide which key verified it. And a secret never renders: the field is
`field(repr=False)`, and `settings.safe_source` — `"shared secret (HS256)"`, or the key ids a JWKS
offers — is what a log line should name instead.

`cryptography` is imported only where a JWKS is actually used, so a shared-secret deployment needs
nothing beyond the standard library. A JWKS is a document, not a URL: fetching one belongs to the
deployment that already owns its trust configuration, and nothing in this package opens a socket.

## What it does not do

- **No OAuth2 flows, no OIDC discovery, no Auth0/Okta/Entra presets.** They were in `0.1.2` and they
  are not coming back. Redirecting, exchanging codes, and refreshing tokens are authorization-server
  concerns; the `0.1.2` source stays in this repository's history for anyone who needs it.
- **No policy.** No roles, no scope checks, no sessions, no tenancy model, no `require_role`. The
  principal is a value the application interprets
  ([ADR 0014](https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0014-no-identity-or-authorization-model.md)).
- **No registration.** No provider, no entry point, no middleware, no discovery of any kind
  ([ADR 0007](https://github.com/xyberos/xyberos2.0/blob/master/docs/adr/0007-trusted-plugins.md)).
- **No secrets in files.** Key material is an explicit settings object or the environment, never a
  committed configuration file, and never a value in an error message.
- **No conformance module.** Core ships no conformance suite for a delegate that owns no framework
  seam, so the manifest keeps this name `planned` and the gate is this package's own tests: an
  unsigned assertion, an expired one, and one minted for another audience are each refused, and each
  has its own test.
