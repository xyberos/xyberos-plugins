"""Auth plugin (RFC-0019, M9): OAuth2, OIDC, JWT with Auth0/Okta/Entra presets."""

from .jwt import JwtCodec
from .oauth2 import OAuth2Client
from .oidc import OidcClient
from .plugin import AuthPlugin
from .presets import OIDC_PRESETS, build_oidc, get_preset

__all__ = [
    "AuthPlugin",
    "JwtCodec",
    "OAuth2Client",
    "OIDC_PRESETS",
    "OidcClient",
    "build_oidc",
    "get_preset",
]
