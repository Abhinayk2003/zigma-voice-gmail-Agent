from __future__ import annotations

from base64 import urlsafe_b64encode
from email.mime.text import MIMEText
from typing import Any

from app.config.settings import get_settings
from app.gmail.service import gmail_service


class GmailDraftService:
    """
    Gmail draft service.

    Creates a Gmail draft without sending it.

    Gmail generates the draft/message/thread identifiers.
    No Gmail identifiers are hard-coded.
    """

    def __init__(self) -> None:
        self.gmail_client = gmail_service
        self.settings = get_settings()

    @staticmethod
    def _normalize_text(value: str) -> str:
        if not value:
            return ""

        text = str(value)

        text = text.replace("\\r\\n", "\n")
        text = text.replace("\\n", "\n")
        text = text.replace("\\r", "\n")

        return text

    def _apply_signature(self, body: str) -> str:
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

        if body.endswith(signature):
            return body

        return (
            f"{body}\n\n"
            f"{signature}"
        ).strip()

    @staticmethod
    def _normalize_recipients(
        value: str | list[str] | None,
    ) -> list[str]:

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

        recipients = []

        for item in values:
            email = str(item).strip()

            if email:
                recipients.append(email)

        return recipients

    @staticmethod
    def _join_recipients(
        recipients: list[str],
    ) -> str | None:

        if not recipients:
            return None

        return ", ".join(recipients)

    def create_draft(
        self,
        account_email: str,
        recipient: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict[str, Any]:

        if not account_email:
            raise ValueError(
                "Authenticated Gmail account is required."
            )

        account_email = account_email.strip()

        if not account_email:
            raise ValueError(
                "Authenticated Gmail account is required."
            )

        recipients = self._normalize_recipients(
            recipient
        )

        if not recipients:
            raise ValueError(
                "At least one recipient email address is required."
            )

        if not subject or not subject.strip():
            raise ValueError(
                "Email subject is required."
            )

        if not body or not body.strip():
            raise ValueError(
                "Email body is required."
            )

        subject = self._normalize_text(
            subject
        ).strip()

        final_body = self._apply_signature(
            body
        )

        cc_recipients = self._normalize_recipients(cc)
        bcc_recipients = self._normalize_recipients(bcc)

        try:
            service = self.gmail_client.get_service(
                account_email
            )
        except Exception as exc:
            raise RuntimeError(
                "Unable to initialize Gmail service."
            ) from exc

        message = MIMEText(
            final_body,
            "plain",
            "utf-8",
        )

        message["To"] = self._join_recipients(
            recipients
        )

        message["Subject"] = subject

        if cc_recipients:
            message["Cc"] = self._join_recipients(
                cc_recipients
            )

        if bcc_recipients:
            message["Bcc"] = self._join_recipients(
                bcc_recipients
            )

        raw_message = urlsafe_b64encode(
            message.as_bytes()
        ).decode("utf-8")

        try:
            response = (
                service.users()
                .drafts()
                .create(
                    userId="me",
                    body={
                        "message": {
                            "raw": raw_message
                        }
                    },
                )
                .execute()
            )

        except Exception as exc:
            raise RuntimeError(
                "Unable to create Gmail draft."
            ) from exc

        draft_id = response.get("id")

        message_data = response.get(
            "message",
            {},
        )

        message_id = message_data.get("id")
        thread_id = message_data.get("threadId")

        return {
            "draft_id": draft_id,
            "message_id": message_id,
            "thread_id": thread_id,
            "recipient": recipient,
            "subject": subject,
            "body": final_body,
            "cc": cc,
            "bcc": bcc,
        }


gmail_draft_service = GmailDraftService()
