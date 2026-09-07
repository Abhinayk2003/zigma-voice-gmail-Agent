from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource
from googleapiclient.discovery import build

from app.auth.credential_service import CredentialService


class GmailClient:
    """
    Creates an authenticated Gmail API client dynamically.

    OAuth credentials are retrieved from AWS Secrets Manager
    through CredentialService.

    No Gmail account, message ID, thread ID, or token is
    hardcoded here.
    """

    def __init__(
        self,
        credential_service: CredentialService | None = None,
    ) -> None:
        self.credential_service = (
            credential_service
            or CredentialService()
        )

    # =========================================================
    # Load credentials
    # =========================================================

    def get_credentials(
        self,
        account_email: str,
    ) -> Credentials:
        """
        Retrieve Gmail credentials for the requested account.
        """

        if not account_email:
            raise ValueError(
                "account_email is required."
            )

        credentials = (
            self.credential_service.get_credentials(
                account_email=account_email
            )
        )

        if not credentials:
            raise ValueError(
                "Gmail credentials were not found."
            )

        # =====================================================
        # Refresh expired credentials
        # =====================================================

        if credentials.expired:

            if not credentials.refresh_token:
                raise ValueError(
                    "Gmail access token has expired and "
                    "no refresh token is available."
                )

            try:

                credentials.refresh(
                    Request()
                )

            except Exception as exc:

                raise RuntimeError(
                    "Unable to refresh Gmail OAuth "
                    "credentials."
                ) from exc

            # -------------------------------------------------
            # Store refreshed credentials securely.
            # -------------------------------------------------

            self.credential_service.store_credentials(
                account_email=account_email,
                credentials=credentials,
            )

        return credentials

    # =========================================================
    # Build Gmail API client
    # =========================================================

    def get_service(
        self,
        account_email: str,
    ) -> Resource:
        """
        Build and return an authenticated Gmail API client.
        """

        credentials = self.get_credentials(
            account_email=account_email
        )

        try:

            service = build(
                "gmail",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )

        except Exception as exc:

            raise RuntimeError(
                "Unable to create Gmail API client."
            ) from exc

        return service