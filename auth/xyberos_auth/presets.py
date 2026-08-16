"""Provider presets for Auth0, Okta and Microsoft Entra (OIDC)."""

from __future__ import annotations

from .oidc import OidcClient

#: preset name -> issuer template. ``{tenant}`` / ``{org}`` are substituted.
OIDC_PRESETS: dict[str, str] = {
    "auth0": "https://{tenant}.auth0.com",
    "okta": "https://{org}.okta.com/oauth2/default",
    "entra": "https://login.microsoftonline.com/{tenant}/v2.0",
}


def get_preset(name: str, **kwargs: str) -> str:
    """Return the issuer for a named OIDC preset, filling in placeholders."""
    key = name.lower()
    if key not in OIDC_PRESETS:
        raise ValueError(f"unknown OIDC preset '{name}' (choose from {sorted(OIDC_PRESETS)})")
    template = OIDC_PRESETS[key]
    missing = [token for token in ("{tenant}", "{org}") if token in template and token[1:-1] not in kwargs]
    if missing:
        raise ValueError(f"preset '{name}' requires a '{missing[0][1:-1]}' value")
    return template.format(**kwargs)


def build_oidc(preset: str, client_id: str, client_secret: str | None = None, **kwargs: str) -> OidcClient:
    """Build an :class:`OidcClient` for a named preset."""
    issuer = get_preset(preset, **kwargs)
    return OidcClient(issuer, client_id=client_id, client_secret=client_secret)
