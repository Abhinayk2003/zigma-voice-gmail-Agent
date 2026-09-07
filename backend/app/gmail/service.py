from __future__ import annotations

from typing import Any

from google.auth.transport.requests import Request
from googleapiclient.discovery import Resource
from googleapiclient.discovery import build

from app.auth.credential_service import CredentialService


class GmailService:
    """
    Central Gmail API service.

    Responsibilities:
    - Load OAuth credentials from AWS Secrets Manager
    - Refresh expired credentials
    - Build the Gmail API client
    - Provide a reusable Gmail API connection

    No Gmail credentials are stored in this class.
    """

    def __init__(self) -> None:

        self.credential_service = CredentialService()

    # =========================================================
    # Build Gmail API client
    # =========================================================

    def get_service(
        self,
        account_email: str,
    ) -> Resource:
        """
        Build and return an authenticated Gmail API client.

        Credentials are loaded dynamically from
        AWS Secrets Manager using the Gmail account email.
        """

        if not account_email:
            raise ValueError(
                "Gmail account email is required."
            )

        credentials = (
            self.credential_service.get_credentials(
                account_email
            )
        )

        # -----------------------------------------------------
        # Refresh expired credentials
        # -----------------------------------------------------

        credentials_refreshed = False

        if credentials.expired:

            if not credentials.refresh_token:
                raise ValueError(
                    "Gmail credentials have expired and "
                    "no refresh token is available."
                )

            credentials.refresh(
                Request()
            )

            credentials_refreshed = True

        # -----------------------------------------------------
        # Store refreshed credentials
        # -----------------------------------------------------

        if credentials_refreshed:

            self.credential_service.store_credentials(
                account_email=account_email,
                credentials=credentials,
            )

        # -----------------------------------------------------
        # Create Gmail API client
        # -----------------------------------------------------

        gmail_service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        return gmail_service

    # =========================================================
    # Gmail profile
    # =========================================================

    def get_profile(
        self,
        account_email: str,
    ) -> dict[str, Any]:
        """
        Retrieve Gmail profile information.
        """

        service = self.get_service(
            account_email
        )

        profile = (
            service.users()
            .getProfile(
                userId="me"
            )
            .execute()
        )

        return profile


# =============================================================
# Shared service instance
# =============================================================

gmail_service = GmailService()