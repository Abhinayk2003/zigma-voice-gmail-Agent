from __future__ import annotations

import os
from typing import Any

from google_auth_oauthlib.flow import Flow

from app.config.settings import get_settings


# =============================================================
# Settings
# =============================================================

settings = get_settings()


# =============================================================
# Google OAuth Scopes
# =============================================================

GOOGLE_SCOPES = [
    "https://mail.google.com/",
]


# =============================================================
# Create Google OAuth Flow
# =============================================================

def create_google_flow(
    state: str | None = None,
    code_verifier: str | None = None,
) -> Flow:
    """
    Create the Google OAuth flow dynamically.

    The same:
        - client ID
        - client secret
        - redirect URI
        - OAuth state
        - PKCE verifier

    are used throughout the OAuth flow.

    No Gmail account, email address, message ID,
    or user-specific value is hard-coded.
    """

    # ---------------------------------------------------------
    # Local development
    # ---------------------------------------------------------

    if settings.google_redirect_uri.startswith(
        "http://localhost"
    ):
        os.environ.setdefault(
            "OAUTHLIB_INSECURE_TRANSPORT",
            "1",
        )

    # ---------------------------------------------------------
    # Validate configuration
    # ---------------------------------------------------------

    if not settings.google_client_id:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID is not configured."
        )

    if not settings.google_client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_SECRET is not configured."
        )

    if not settings.google_redirect_uri:
        raise RuntimeError(
            "GOOGLE_REDIRECT_URI is not configured."
        )

    # ---------------------------------------------------------
    # Google client configuration
    # ---------------------------------------------------------

    client_config: dict[str, Any] = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,

            "auth_uri": (
                "https://accounts.google.com/o/oauth2/auth"
            ),

            "token_uri": (
                "https://oauth2.googleapis.com/token"
            ),

            "redirect_uris": [
                settings.google_redirect_uri,
            ],
        }
    }

    # ---------------------------------------------------------
    # Create OAuth flow
    # ---------------------------------------------------------

    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        state=state,
        code_verifier=code_verifier,
    )

    # ---------------------------------------------------------
    # Explicit redirect URI
    # ---------------------------------------------------------

    flow.redirect_uri = (
        settings.google_redirect_uri
    )

    return flow