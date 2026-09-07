from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.auth.credential_service import CredentialService
from app.auth.google_oauth import create_google_flow


# ============================================================================
# Logging
# ============================================================================

logger = logging.getLogger(__name__)


# ============================================================================
# Router
# ============================================================================

router = APIRouter(
    prefix="/auth/google",
    tags=["Google Authentication"],
)


# ============================================================================
# Services
# ============================================================================

credential_service = CredentialService()


# ============================================================================
# Configuration helpers
# ============================================================================

def get_frontend_url() -> str:
    """
    Return the frontend URL used after OAuth authentication.

    Recommended environment variable:

        FRONTEND_URL=http://localhost:5173

    This keeps the frontend location configurable and avoids
    hard-coding application-specific deployment information.
    """

    frontend_url = os.getenv(
        "FRONTEND_URL",
        "http://localhost:5173",
    )

    return frontend_url.rstrip("/")


# ============================================================================
# Utility
# ============================================================================

def normalize_email(
    email: Any,
) -> str:
    """
    Normalize an authenticated Gmail account email.
    """

    if not isinstance(
        email,
        str,
    ):
        return ""

    return email.strip().lower()


# ============================================================================
# Google Login
# ============================================================================

@router.get("/login")
async def google_login(
    request: Request,
):
    """
    Start Google OAuth authorization.

    The following temporary values are stored in the
    server-side session cookie:

        google_oauth_state
        google_code_verifier

    The actual Gmail credentials are NOT stored in the
    browser session. They are stored using CredentialService.
    """

    logger.info("=" * 70)
    logger.info("STARTING GOOGLE OAUTH LOGIN")
    logger.info("=" * 70)

    try:

        # ====================================================================
        # Create OAuth flow
        # ====================================================================

        flow = create_google_flow()

        logger.info(
            "OAuth redirect URI: %s",
            flow.redirect_uri,
        )

        # ====================================================================
        # Generate Google authorization URL
        # ====================================================================

        authorization_url, state = (
            flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
        )

        # ====================================================================
        # PKCE verifier
        # ====================================================================

        code_verifier = flow.code_verifier

        if not code_verifier:

            logger.error(
                "Google OAuth PKCE verifier was not generated."
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Google OAuth PKCE code verifier "
                    "could not be generated."
                ),
            )

        # ====================================================================
        # Store temporary OAuth state
        # ====================================================================

        request.session[
            "google_oauth_state"
        ] = state

        # ====================================================================
        # Store temporary PKCE verifier
        # ====================================================================

        request.session[
            "google_code_verifier"
        ] = code_verifier

        # ====================================================================
        # Clear any old authentication state before starting
        # a completely new Google login.
        # ====================================================================

        request.session.pop(
            "google_account_email",
            None,
        )

        logger.info(
            "OAuth state stored: %s",
            bool(
                request.session.get(
                    "google_oauth_state"
                )
            ),
        )

        logger.info(
            "PKCE verifier stored: %s",
            bool(
                request.session.get(
                    "google_code_verifier"
                )
            ),
        )

        logger.info("=" * 70)

        # ====================================================================
        # Redirect browser to Google
        # ====================================================================

        return RedirectResponse(
            url=authorization_url,
            status_code=307,
        )

    except HTTPException:
        raise

    except Exception as exc:

        logger.exception(
            "GOOGLE OAUTH LOGIN FAILED"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to start Google OAuth login."
            ),
        ) from exc


# ============================================================================
# Google Callback
# ============================================================================

@router.get("/callback")
async def google_callback(
    request: Request,
):
    """
    Handle the Google OAuth callback.

    Complete flow:

        Browser
           ↓
        Google
           ↓
        authorization code
           ↓
        state validation
           ↓
        PKCE validation
           ↓
        token exchange
           ↓
        Gmail profile
           ↓
        authenticated Gmail account
           ↓
        AWS Secrets Manager
           ↓
        browser session
           ↓
        frontend

    IMPORTANT:

    The frontend receives only the authentication result.
    Google credentials are never sent to the frontend.
    """

    logger.info("=" * 70)
    logger.info("GOOGLE OAUTH CALLBACK")
    logger.info("=" * 70)

    frontend_url = get_frontend_url()

    # =========================================================================
    # 1. Check OAuth error
    # =========================================================================

    error = request.query_params.get(
        "error"
    )

    if error:

        error_description = (
            request.query_params.get(
                "error_description"
            )
        )

        logger.error(
            "Google OAuth authorization failed: %s",
            error,
        )

        if error_description:

            logger.error(
                "Google OAuth error description: %s",
                error_description,
            )

        # ---------------------------------------------------------------------
        # Clear temporary OAuth session values.
        # ---------------------------------------------------------------------

        request.session.pop(
            "google_oauth_state",
            None,
        )

        request.session.pop(
            "google_code_verifier",
            None,
        )

        # ---------------------------------------------------------------------
        # Return user to frontend.
        #
        # The frontend can display a generic authentication error.
        # ---------------------------------------------------------------------

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 2. Read callback parameters
    # =========================================================================

    code = request.query_params.get(
        "code"
    )

    state = request.query_params.get(
        "state"
    )

    logger.info(
        "Authorization code received: %s",
        bool(code),
    )

    logger.info(
        "OAuth state received: %s",
        bool(state),
    )

    if not code:

        logger.error(
            "Google authorization code missing."
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    if not state:

        logger.error(
            "Google OAuth state missing."
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 3. Read expected state from session
    # =========================================================================

    expected_state = (
        request.session.get(
            "google_oauth_state"
        )
    )

    logger.info(
        "Expected OAuth state exists: %s",
        bool(expected_state),
    )

    if not expected_state:

        logger.error(
            "OAuth state is missing from the browser session."
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 4. Validate OAuth state
    # =========================================================================

    if state != expected_state:

        logger.error(
            "OAuth state mismatch."
        )

        request.session.pop(
            "google_oauth_state",
            None,
        )

        request.session.pop(
            "google_code_verifier",
            None,
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    logger.info(
        "OAuth state validation: OK"
    )

    # =========================================================================
    # 5. Read PKCE verifier
    # =========================================================================

    code_verifier = (
        request.session.get(
            "google_code_verifier"
        )
    )

    logger.info(
        "PKCE verifier exists: %s",
        bool(code_verifier),
    )

    if not code_verifier:

        logger.error(
            "OAuth PKCE verifier missing from session."
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 6. Create callback OAuth flow
    # =========================================================================

    try:

        flow = create_google_flow(
            state=expected_state,
            code_verifier=code_verifier,
        )

        logger.info(
            "Callback OAuth redirect URI: %s",
            flow.redirect_uri,
        )

    except Exception as exc:

        logger.exception(
            "GOOGLE OAUTH FLOW CREATION FAILED"
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 7. Build authorization response
    # =========================================================================

    authorization_response = str(
        request.url
    )

    # =========================================================================
    # 8. Exchange authorization code for credentials
    # =========================================================================

    try:

        logger.info(
            "Exchanging Google authorization code..."
        )

        flow.fetch_token(
            authorization_response=(
                authorization_response
            )
        )

        logger.info(
            "Google token exchange successful."
        )

    except Exception as exc:

        logger.exception(
            "GOOGLE OAUTH TOKEN EXCHANGE FAILED"
        )

        request.session.pop(
            "google_oauth_state",
            None,
        )

        request.session.pop(
            "google_code_verifier",
            None,
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 9. Get Google credentials
    # =========================================================================

    credentials = flow.credentials

    if not credentials:

        logger.error(
            "Google OAuth returned no credentials."
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    if not credentials.token:

        logger.error(
            "Google OAuth returned no access token."
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    logger.info(
        "Google credentials successfully received."
    )

    # =========================================================================
    # 10. Get Gmail profile
    # =========================================================================

    try:

        gmail_api = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        profile: dict[str, Any] = (
            gmail_api.users()
            .getProfile(
                userId="me"
            )
            .execute()
        )

        logger.info(
            "Gmail profile successfully retrieved."
        )

    except HttpError as exc:

        logger.exception(
            "GMAIL PROFILE FETCH FAILED"
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    except Exception as exc:

        logger.exception(
            "GMAIL PROFILE FETCH FAILED"
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 11. Extract authenticated Gmail account
    # =========================================================================

    account_email = normalize_email(
        profile.get(
            "emailAddress"
        )
    )

    if not account_email:

        logger.error(
            "Unable to determine authenticated Gmail account."
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    logger.info(
        "Authenticated Gmail account: %s",
        account_email,
    )

    # =========================================================================
    # 12. Store credentials securely
    # =========================================================================

    try:

        secret_reference = (
            credential_service.store_credentials(
                account_email=account_email,
                credentials=credentials,
            )
        )

        logger.info(
            "Gmail credentials stored successfully."
        )

    except Exception as exc:

        logger.exception(
            "AWS CREDENTIAL STORAGE FAILED"
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 13. Store authenticated account in browser session
    # =========================================================================
    #
    # THIS IS THE IMPORTANT PART FOR YOUR CURRENT ISSUE.
    #
    # The frontend/WebSocket later reads:
    #
    #     google_account_email
    #
    # from the same session cookie.
    #
    # ==========================================================================

    request.session[
        "google_account_email"
    ] = account_email

    logger.info(
        "Authenticated Gmail account stored in session: %s",
        request.session.get(
            "google_account_email"
        ),
    )

    # =========================================================================
    # 14. Store authentication status explicitly
    # =========================================================================

    request.session[
        "google_authenticated"
    ] = True

    # =========================================================================
    # 15. Remove one-time OAuth values
    # =========================================================================

    request.session.pop(
        "google_oauth_state",
        None,
    )

    request.session.pop(
        "google_code_verifier",
        None,
    )

    # =========================================================================
    # 16. Verify session values before redirect
    # =========================================================================

    session_account = normalize_email(
        request.session.get(
            "google_account_email"
        )
    )

    session_authenticated = (
        request.session.get(
            "google_authenticated"
        )
        is True
    )

    logger.info(
        "FINAL SESSION CHECK | authenticated=%s | account=%s",
        session_authenticated,
        session_account or "NONE",
    )

    if (
        not session_authenticated
        or session_account != account_email
    ):

        logger.error(
            "Authentication session verification failed."
        )

        return RedirectResponse(
            url=(
                f"{frontend_url}"
                "/?auth=error"
            ),
            status_code=303,
        )

    # =========================================================================
    # 17. OAuth success
    # =========================================================================

    logger.info("=" * 70)
    logger.info("GOOGLE OAUTH SUCCESS")
    logger.info(
        "Authenticated account: %s",
        account_email,
    )
    logger.info(
        "Credentials stored: True"
    )
    logger.info(
        "Session authenticated: True"
    )
    logger.info("=" * 70)

    # =========================================================================
    # 18. Redirect to frontend
    # =========================================================================
    #
    # IMPORTANT:
    #
    # Do NOT return the credentials or secret reference to the browser.
    #
    # The browser only needs to know that authentication completed.
    #
    # The frontend will call:
    #
    #     GET /auth/google/session
    #
    # to obtain the current authenticated account.
    #
    # ==========================================================================

    return RedirectResponse(
        url=(
            f"{frontend_url}"
            "/?auth=success"
        ),
        status_code=303,
    )


# ============================================================================
# Session Verification
# ============================================================================

@router.get("/session")
async def check_google_session(
    request: Request,
):
    """
    Return the authentication status of the current browser session.

    This endpoint is intended for the frontend.

    The frontend should call:

        GET /auth/google/session

    with credentials/cookies enabled.
    """

    account_email = normalize_email(
        request.session.get(
            "google_account_email"
        )
    )

    authenticated_flag = (
        request.session.get(
            "google_authenticated"
        )
        is True
    )

    # ------------------------------------------------------------------------
    # Authentication is considered valid only when BOTH values are present.
    # ------------------------------------------------------------------------

    authenticated = bool(
        account_email
        and authenticated_flag
    )

    # ------------------------------------------------------------------------
    # If the session is inconsistent, clean it up.
    # ------------------------------------------------------------------------

    if not authenticated:

        request.session.pop(
            "google_account_email",
            None,
        )

        request.session.pop(
            "google_authenticated",
            None,
        )

        account_email = None

    logger.info(
        "GOOGLE SESSION CHECK | authenticated=%s | account=%s",
        authenticated,
        account_email or "NONE",
    )

    return {
        "authenticated": authenticated,
        "account_email": account_email,
    }


# ============================================================================
# Logout
# ============================================================================

@router.get("/logout")
async def google_logout(
    request: Request,
):
    """
    Clear the current Google/Gmail browser authentication session.

    Gmail credentials stored in AWS Secrets Manager are NOT deleted here.

    This endpoint only logs the browser session out.
    """

    previous_account = normalize_email(
        request.session.get(
            "google_account_email"
        )
    )

    # =========================================================================
    # Clear authentication session
    # =========================================================================

    request.session.pop(
        "google_account_email",
        None,
    )

    request.session.pop(
        "google_authenticated",
        None,
    )

    # =========================================================================
    # Clear temporary OAuth values
    # =========================================================================

    request.session.pop(
        "google_oauth_state",
        None,
    )

    request.session.pop(
        "google_code_verifier",
        None,
    )

    logger.info(
        "Google session cleared. Previous account: %s",
        previous_account or "NONE",
    )

    return {
        "success": True,
        "authenticated": False,
        "account_email": None,
        "message": (
            "Google Gmail session cleared."
        ),
    }