# xyberos-auth

**Auth plugin — RFC-0019, M9.** OAuth 2.0, OpenID Connect, and JWT, with
Auth0 / Okta / Microsoft Entra presets. All stdlib (`urllib` + `hmac`); RS256
uses lazy `cryptography`.

## Install

```bash
pip install xyberos-auth            # from PyPI

# development (editable, from this repo):
pip install -e ./auth
```

## JWT

```python
from xyberos_auth import JwtCodec

codec = JwtCodec("a-shared-secret")
token = codec.encode({"sub": "user-1"}, ttl=3600)
codec.decode(token, verify=True)   # raises AuthError on tamper/expiry
```

Or through the plugin (HS256 via `AUTH_JWT_SECRET`):

```python
from xyberos import create_app
from xyberos_auth import AuthPlugin

app = create_app()
app.load_plugin(AuthPlugin(secret="dev-secret"))
app.tools.execute("jwt_sign", None, payload={"sub": "user-1"}, ttl=600)
app.tools.execute("jwt_verify", None, token=token)
```

## OAuth2 / OIDC

```python
from xyberos_auth import OAuth2Client, build_oidc

oauth2 = OAuth2Client("cid", "csecret",
                      authorize_url="https://idp/authorize",
                      token_url="https://idp/token", scope="openid profile")
url = oauth2.authorization_url(state="abc")
tokens = oauth2.exchange_code("code")

oidc = build_oidc("auth0", client_id="cid", client_secret="csecret", tenant="myco")
user = oidc.userinfo(tokens["access_token"])
claims = oidc.verify_id_token(tokens.get("id_token", ""))
```

Presets: `auth0` (`{tenant}`), `okta` (`{org}`), `entra` (`{tenant}`).

## Tests

```bash
pip install pytest
pytest tests/
```

Transport-injectable (OAuth2/OIDC) + real HMAC/RSA JWT tests (skip RS256 when
`cryptography` is absent).

## Ship location

Plugin (`xyberos.plugins` entry point) — enterprise auth (M9).
