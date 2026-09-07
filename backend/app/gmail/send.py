from __future__ import annotations

from base64 import urlsafe_b64encode
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.errors import HttpError

from app.config.settings import get_settings
from app.gmail.service import gmail_service


class GmailSendService:
    """
    Gmail send service.

    Responsibilities:
    - Dynamically send new Gmail emails
    - Dynamically handle recipients, CC and BCC
    - Apply configurable signature
    - Normalize escaped newline characters
    - Return Gmail-generated message/thread IDs

    No Gmail IDs, recipient addresses, subjects,
    signatures, or message content are hardcoded.
    """

    def __init__(self) -> None:
        self.gmail_client = gmail_service
        self.settings = get_settings()

    # =========================================================
    # Text Normalization
    # =========================================================

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        """
        Normalize text received from the application/LLM.

        Important:
        If configuration contains:

            Regards,\\nAbhinay Kotha\\nExclCloud Solutions

        convert the literal '\\n' characters into actual
        newline characters:

            Regards,
            Abhinay Kotha
            ExclCloud Solutions

        Real newline characters are preserved.
        """

        if not value:
            return ""

        text = str(value)

        # Convert literal escaped newline sequences
        # into actual newline characters.
        text = text.replace("\\r\\n", "\n")
        text = text.replace("\\n", "\n")
        text = text.replace("\\r", "\n")

        return text

    # =========================================================
    # Signature
    # =========================================================

    def _apply_signature(
        self,
        body: str,
    ) -> str:
        """
        Apply the configured email signature.

        Signature comes entirely from application settings.
        """

        if not body or not body.strip():
            return body

        body = self._normalize_text(body).strip()

        if not self.settings.email_signature_enabled:
            return body

        signature = (
            self.settings.email_signature
            or ""
        )

        signature = self._normalize_text(
            signature
        ).strip()

        if not signature:
            return body

        # Avoid adding the same signature twice.
        if body.endswith(signature):
            return body

        return (
            f"{body}\n\n"
            f"{signature}"
        ).strip()

    # =========================================================
    # Normalize Email List
    # =========================================================

    @staticmethod
    def _normalize_recipients(
        value: str | list[str] | None,
    ) -> list[str]:
        """
        Normalize recipient values.

        Supported:

            "user@example.com"

            "user1@example.com,user2@example.com"

            [
                "user1@example.com",
                "user2@example.com"
            ]
        """

        if value is None:
            return []

        if isinstance(value, str):

            values = value.split(",")

        elif isinstance(value, list):

            values = value

        else:

            raise ValueError(
                "Email recipients must be a string or list."
            )

        recipients: list[str] = []

        for item in values:

            email = str(
                item
            ).strip()

            if email:
                recipients.append(
                    email
                )

        return recipients

    # =========================================================
    # Join Recipients
    # =========================================================

    @staticmethod
    def _join_recipients(
        recipients: list[str],
    ) -> str | None:
        """
        Convert recipient list into an email header value.
        """

        if not recipients:
            return None

        return ", ".join(
            recipients
        )

    # =========================================================
    # Send Email
    # =========================================================

    def send_email(
        self,
        account_email: str,
        recipient: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Send a new Gmail email.

        Gmail generates the message ID and thread ID.
        """

        # -----------------------------------------------------
        # Validate account
        # -----------------------------------------------------

        if not account_email:
            raise ValueError(
                "Authenticated Gmail account is required."
            )

        account_email = account_email.strip()

        if not account_email:
            raise ValueError(
                "Authenticated Gmail account is required."
            )

        # -----------------------------------------------------
        # Normalize recipients
        # -----------------------------------------------------

        recipients = self._normalize_recipients(
            recipient
        )

        if not recipients:
            raise ValueError(
                "At least one recipient email address is required."
            )

        # -----------------------------------------------------
        # Validate subject
        # -----------------------------------------------------

        if not subject or not subject.strip():

            raise ValueError(
                "Email subject is required."
            )

        subject = self._normalize_text(
            subject
        ).strip()

        # -----------------------------------------------------
        # Validate body
        # -----------------------------------------------------

        if not body or not body.strip():

            raise ValueError(
                "Email body is required."
            )

        # -----------------------------------------------------
        # Normalize optional recipients
        # -----------------------------------------------------

        cc_recipients = (
            self._normalize_recipients(cc)
        )

        bcc_recipients = (
            self._normalize_recipients(bcc)
        )

        # -----------------------------------------------------
        # Apply configurable signature
        # -----------------------------------------------------

        final_body = self._apply_signature(
            body
        )

        # -----------------------------------------------------
        # Build Gmail service
        # -----------------------------------------------------

        try:

            service = self.gmail_client.get_service(
                account_email
            )

        except Exception as exc:

            raise RuntimeError(
                "Unable to initialize Gmail service."
            ) from exc

        # -----------------------------------------------------
        # Build MIME message
        # -----------------------------------------------------

        message = MIMEText(
            final_body,
            "plain",
            "utf-8",
        )

        to_header = self._join_recipients(
            recipients
        )

        if to_header:
            message["To"] = to_header

        message["Subject"] = subject

        cc_header = self._join_recipients(
            cc_recipients
        )

        if cc_header:
            message["Cc"] = cc_header

        bcc_header = self._join_recipients(
            bcc_recipients
        )

        if bcc_header:
            message["Bcc"] = bcc_header

        # -----------------------------------------------------
        # Encode MIME message
        # -----------------------------------------------------

        raw_message = urlsafe_b64encode(
            message.as_bytes()
        ).decode("utf-8")

        request_body: dict[str, Any] = {
            "raw": raw_message,
        }

        # -----------------------------------------------------
        # Send through Gmail API
        # -----------------------------------------------------

        try:

            response = (
                service.users()
                .messages()
                .send(
                    userId="me",
                    body=request_body,
                )
                .execute()
            )

        except HttpError as exc:

            print("=" * 70)
            print("GMAIL SEND FAILED")
            print(
                "Account:",
                account_email,
            )
            print(
                "Recipients:",
                recipients,
            )
            print(
                "Status:",
                getattr(
                    exc.resp,
                    "status",
                    None,
                ),
            )
            print(
                "Exception:",
                str(exc),
            )
            print("=" * 70)

            raise RuntimeError(
                "Unable to send Gmail email."
            ) from exc

        # -----------------------------------------------------
        # Gmail-generated identifiers
        # -----------------------------------------------------

        message_id = response.get(
            "id"
        )

        thread_id = response.get(
            "threadId"
        )

        return {
            "success": True,
            "intent": "send",
            "message_id": message_id,
            "thread_id": thread_id,
            "account_email": account_email,
            "recipients": recipients,
            "cc": cc_recipients,
            "bcc": bcc_recipients,
            "subject": subject,
            "body": final_body,
        }


# =============================================================
# Shared Service Instance
# =============================================================

gmail_send_service = GmailSendService()