"""Errors raised by the auth plugin."""

from __future__ import annotations


class AuthError(Exception):
    """An OAuth/OIDC/JWT failure."""
