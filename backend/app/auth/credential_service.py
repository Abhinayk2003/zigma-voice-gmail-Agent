import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError
from google.oauth2.credentials import Credentials

from app.config.settings import get_settings


settings = get_settings()


class CredentialService:
    """
    Secure credential management for Gmail accounts.

    OAuth credentials are stored in AWS Secrets Manager.
    They are never stored in PostgreSQL.

    The secret identifier is generated dynamically from
    the authenticated Gmail account.
    """

    def __init__(self) -> None:

        self.client = boto3.client(
            "secretsmanager",
            region_name=settings.aws_region,
        )

    # =========================================================
    # Dynamic secret identifier
    # =========================================================

    def _build_secret_name(
        self,
        account_email: str,
    ) -> str:
        """
        Generate a deterministic secret name from
        the Gmail account.

        The actual email address is not placed directly
        in the secret name.
        """

        normalized_email = (
            account_email.strip().lower()
        )

        account_hash = hashlib.sha256(
            normalized_email.encode("utf-8")
        ).hexdigest()[:32]

        return (
            f"{settings.aws_secret_prefix}/"
            f"{account_hash}"
        )

    # =========================================================
    # Store credentials
    # =========================================================

    def store_credentials(
        self,
        account_email: str,
        credentials: Credentials,
    ) -> str:
        """
        Store Gmail OAuth credentials in AWS Secrets Manager.

        Returns the generated secret name.

        Access and refresh tokens are NEVER returned to
        the caller.
        """

        secret_name = self._build_secret_name(
            account_email
        )

        secret_payload = {
            "account_email": account_email,
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": (
                credentials.expiry.isoformat()
                if credentials.expiry
                else None
            ),
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        secret_string = json.dumps(
            secret_payload
        )

        try:

            self.client.put_secret_value(
                SecretId=secret_name,
                SecretString=secret_string,
            )

        except self.client.exceptions.ResourceNotFoundException:

            self.client.create_secret(
                Name=secret_name,
                Description=(
                    "Zigma Voice Gmail Agent "
                    "OAuth credentials"
                ),
                SecretString=secret_string,
            )

        return secret_name

    # =========================================================
    # Retrieve credentials
    # =========================================================

    def get_credentials(
        self,
        account_email: str,
    ) -> Credentials:
        """
        Retrieve Gmail OAuth credentials from
        AWS Secrets Manager.
        """

        secret_name = self._build_secret_name(
            account_email
        )

        try:

            response = self.client.get_secret_value(
                SecretId=secret_name
            )

        except ClientError as exc:

            error_code = exc.response.get(
                "Error",
                {},
            ).get(
                "Code"
            )

            if error_code == "ResourceNotFoundException":

                raise ValueError(
                    "Gmail credentials were not "
                    "found for this account."
                ) from exc

            raise

        secret_string = response.get(
            "SecretString"
        )

        if not secret_string:

            raise ValueError(
                "Gmail credential secret is empty."
            )

        payload: dict[str, Any] = json.loads(
            secret_string
        )

        expiry = payload.get(
            "expiry"
        )

        parsed_expiry = None

        if expiry:

            parsed_expiry = datetime.fromisoformat(
                expiry
            )

        return Credentials(
            token=payload.get("token"),
            refresh_token=payload.get(
                "refresh_token"
            ),
            token_uri=payload.get(
                "token_uri"
            ),
            client_id=payload.get(
                "client_id"
            ),
            client_secret=payload.get(
                "client_secret"
            ),
            scopes=payload.get(
                "scopes"
            ),
            expiry=parsed_expiry,
        )

    # =========================================================
    # Delete credentials
    # =========================================================

    def delete_credentials(
        self,
        account_email: str,
    ) -> None:
        """
        Permanently remove credentials for a Gmail account.
        """

        secret_name = self._build_secret_name(
            account_email
        )

        try:

            self.client.delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True,
            )

        except self.client.exceptions.ResourceNotFoundException:

            return