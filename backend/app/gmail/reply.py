from __future__ import annotations

from base64 import urlsafe_b64encode
from email.mime.text import MIMEText
from email.utils import getaddresses, parseaddr
from typing import Any

from googleapiclient.errors import HttpError

from app.config.settings import get_settings
from app.gmail.service import gmail_service
from difflib import SequenceMatcher


class GmailReplyService:
    """
    Gmail reply service.

    Responsibilities:
        - Dynamically retrieve the original Gmail message.
        - Preserve Gmail thread information.
        - Dynamically determine the reply recipient.
        - Prevent replies from being sent back to the
          authenticated user's own email address.
        - Build In-Reply-To and References headers.
        - Apply configurable signature.
        - Apply configurable automated email note.
        - Send the reply inside the existing Gmail thread.

    No Gmail message ID, thread ID, recipient, signature,
    or automated note is hardcoded.
    """

    def __init__(self) -> None:

        self.gmail_client = gmail_service

        self.settings = get_settings()

    # =========================================================
    # Header Helper
    # =========================================================

    @staticmethod
    def _get_header(
        headers: list[dict[str, Any]],
        name: str,
    ) -> str | None:
        """
        Retrieve a Gmail message header dynamically.

        Header matching is case-insensitive.
        """

        target = (
            name.strip()
            .lower()
        )

        for header in headers:

            if not isinstance(
                header,
                dict,
            ):
                continue

            header_name = str(
                header.get(
                    "name",
                    "",
                )
            ).strip().lower()

            if header_name == target:

                value = header.get(
                    "value"
                )

                if value is not None:
                    return str(value)

        return None

    # =========================================================
    # Normalize Configured Text
    # =========================================================

    @staticmethod
    def _normalize_configured_text(
        value: str | None,
    ) -> str:
        """
        Convert escaped newline sequences into actual
        newline characters.

        Example:

            Regards,\\nAbhinay

        becomes:

            Regards,
            Abhinay

        This also handles values that were escaped
        multiple times.
        """

        if value is None:
            return ""

        text = str(value)

        previous = None

        while text != previous:

            previous = text

            text = text.replace(
                "\\r\\n",
                "\n",
            )

            text = text.replace(
                "\\n",
                "\n",
            )

            text = text.replace(
                "\\r",
                "\n",
            )

        return text
    # =========================================================
    # Email Footer
    # =========================================================

    def _apply_email_footer(
        self,
        body: str,
    ) -> str:
        """
        Build the final reply body.

        Order:

            User body
                ↓
            Signature
                ↓
            Automated note

        Any existing version of the configured automated note
        is removed before the signature is added.

        The comparison is normalized so small differences in:
            - capitalization
            - punctuation
            - spacing
            - "the"
        do not cause duplicate automated notes.
        """

        if not body or not body.strip():

            return body

        # -----------------------------------------------------
        # Normalize body
        # -----------------------------------------------------

        final_body = (
            self._normalize_configured_text(
                body
            )
            .strip()
        )

        # =====================================================
        # Get configured automated note
        # =====================================================

        automated_note = (
            self.settings.email_automated_note
            or ""
        )

        automated_note = (
            self._normalize_configured_text(
                automated_note
            ).strip()
        )

        # =====================================================
        # Remove existing automated note
        # =====================================================

        if automated_note:

            # Create a comparison-friendly version.
            #
            # Example:
            #
            # "Note : This Email is automatically generated
            #  by the computer"
            #
            # becomes approximately:
            #
            # "note this email is automatically generated
            #  by the computer"

            def normalize_for_comparison(
                value: str,
            ) -> str:

                value = value.lower()

                chars: list[str] = []

                for char in value:

                    if char.isalnum() or char.isspace():

                        chars.append(char)

                    else:

                        chars.append(" ")

                return " ".join(
                    "".join(chars).split()
                )

            normalized_note = (
                normalize_for_comparison(
                    automated_note
                )
            )

            # -------------------------------------------------
            # Check individual paragraphs.
            # -------------------------------------------------

            paragraphs = final_body.split("\n\n")

            cleaned_paragraphs: list[str] = []

            for paragraph in paragraphs:

                normalized_paragraph = (
                    normalize_for_comparison(
                        paragraph
                    )
                )

                if not normalized_paragraph:

                    continue

                similarity = (
                    SequenceMatcher(
                        None,
                        normalized_paragraph,
                        normalized_note,
                    ).ratio()
                )

                # Remove only paragraphs that are very close
                # to the configured automated note.
                if similarity >= 0.80:

                    continue

                cleaned_paragraphs.append(
                    paragraph.strip()
                )

            final_body = "\n\n".join(
                cleaned_paragraphs
            ).strip()

        # =====================================================
        # Signature
        # =====================================================

        if self.settings.email_signature_enabled:

            signature = (
                self.settings.email_signature
                or ""
            )

            signature = (
                self._normalize_configured_text(
                    signature
                ).strip()
            )

            if signature:

                if signature not in final_body:

                    final_body = (
                        f"{final_body}\n\n"
                        f"{signature}"
                    )

        # =====================================================
        # Automated Note
        # =====================================================

        if (
            self.settings.email_automated_note_enabled
            and automated_note
        ):

            final_body = (
                f"{final_body}\n\n"
                f"{automated_note}"
            )

        # -----------------------------------------------------
        # Final normalization
        # -----------------------------------------------------

        return (
            self._normalize_configured_text(
                final_body
            ).strip()
        )

    # =========================================================
    # Extract One Email Address
    # =========================================================

    @staticmethod
    def _extract_email_address(
        value: str | None,
    ) -> str | None:
        """
        Extract a clean email address from a Gmail header.

        Example:

            Abhinay Kotha <abhinay@example.com>

        becomes:

            abhinay@example.com
        """

        if not value:
            return None

        _, email_address = parseaddr(
            str(value)
        )

        email_address = (
            email_address
            or str(value)
        ).strip()

        if not email_address:
            return None

        return email_address

    # =========================================================
    # Extract Multiple Email Addresses
    # =========================================================

    @staticmethod
    def _extract_all_email_addresses(
        value: str | None,
    ) -> list[str]:
        """
        Extract all email addresses from a Gmail header.

        Supports:

            John <john@example.com>

        and:

            John <john@example.com>,
            Jane <jane@example.com>
        """

        if not value:
            return []

        addresses: list[str] = []

        for _, address in getaddresses(
            [str(value)]
        ):

            if not address:
                continue

            address = address.strip()

            if address:
                addresses.append(
                    address
                )

        return addresses

    # =========================================================
    # Determine Reply Recipient
    # =========================================================

    def _determine_reply_recipient(
        self,
        headers: list[dict[str, Any]],
        account_email: str,
    ) -> str:
        """
        Determine the correct reply recipient dynamically.

        IMPORTANT:

        There are two different cases.

        -------------------------------------------------------
        CASE 1 - Incoming email
        -------------------------------------------------------

        Example:

            From: person@example.com
            To:   authenticated-user@example.com

        Reply goes to:

            person@example.com

        Priority:

            Reply-To
                ↓
            From

        -------------------------------------------------------
        CASE 2 - Our own sent email
        -------------------------------------------------------

        Example:

            From: authenticated-user@example.com
            To:   person@example.com

        Reply must NOT go to From.

        Instead:

            To
                ↓
            Cc

        This prevents the agent from replying to itself.

        No email address is hardcoded.
        """

        if not account_email:

            raise ValueError(
                "Authenticated Gmail account is required."
            )

        account_email = (
            account_email.strip().lower()
        )

        if not account_email:

            raise ValueError(
                "Authenticated Gmail account is required."
            )

        # =====================================================
        # Get From
        # =====================================================

        from_header = self._get_header(
            headers,
            "From",
        )

        from_address = (
            self._extract_email_address(
                from_header
            )
            if from_header
            else None
        )

        if from_address:

            from_address = (
                from_address.strip().lower()
            )

        # =====================================================
        # CASE 1:
        #
        # Selected message was sent by us.
        #
        # Do NOT use From.
        # =====================================================

        if (
            from_address
            and from_address == account_email
        ):

            # -------------------------------------------------
            # First try To
            # -------------------------------------------------

            to_header = self._get_header(
                headers,
                "To",
            )

            if to_header:

                to_addresses = (
                    self._extract_all_email_addresses(
                        to_header
                    )
                )

                for address in to_addresses:

                    normalized = (
                        address.strip().lower()
                    )

                    if (
                        normalized
                        and normalized != account_email
                    ):

                        return normalized

            # -------------------------------------------------
            # If To does not contain another recipient,
            # try Cc.
            # -------------------------------------------------

            cc_header = self._get_header(
                headers,
                "Cc",
            )

            if cc_header:

                cc_addresses = (
                    self._extract_all_email_addresses(
                        cc_header
                    )
                )

                for address in cc_addresses:

                    normalized = (
                        address.strip().lower()
                    )

                    if (
                        normalized
                        and normalized != account_email
                    ):

                        return normalized

            raise ValueError(
                "Unable to determine the original recipient "
                "for this sent email."
            )

        # =====================================================
        # CASE 2:
        #
        # Incoming email.
        #
        # Prefer Reply-To.
        # =====================================================

        reply_to = self._get_header(
            headers,
            "Reply-To",
        )

        if reply_to:

            reply_address = (
                self._extract_email_address(
                    reply_to
                )
            )

            if reply_address:

                normalized = (
                    reply_address.strip().lower()
                )

                if normalized != account_email:

                    return normalized

        # =====================================================
        # Fall back to From
        # =====================================================

        if from_address:

            if from_address != account_email:

                return from_address

        raise ValueError(
            "Unable to determine the reply recipient."
        )

    # =========================================================
    # Build References
    # =========================================================

    def _build_references(
        self,
        headers: list[dict[str, Any]],
        message_id: str | None,
    ) -> str:
        """
        Build the References header dynamically.

        Existing References are preserved and the original
        Message-ID is appended when necessary.
        """

        references: list[str] = []

        existing_references = (
            self._get_header(
                headers,
                "References",
            )
        )

        if existing_references:

            for reference in (
                existing_references.split()
            ):

                reference = reference.strip()

                if (
                    reference
                    and reference not in references
                ):

                    references.append(
                        reference
                    )

        if message_id:

            message_id = (
                message_id.strip()
            )

            if (
                message_id
                and message_id not in references
            ):

                references.append(
                    message_id
                )

        return " ".join(
            references
        )

    # =========================================================
    # Reply
    # =========================================================

    def reply_to_message(
        self,
        account_email: str,
        message_id: str,
        body: str,
    ) -> dict[str, Any]:
        """
        Reply to an existing Gmail message.

        Gmail dynamically supplies:

            - message ID
            - thread ID

        The existing Gmail thread is preserved.

        The recipient is dynamically determined from
        the original message headers.
        """

        # =====================================================
        # Validate Account
        # =====================================================

        if not account_email:

            raise ValueError(
                "Authenticated Gmail account is required."
            )

        account_email = (
            account_email.strip().lower()
        )

        if not account_email:

            raise ValueError(
                "Authenticated Gmail account is required."
            )

        # =====================================================
        # Validate Message ID
        # =====================================================

        if (
            not message_id
            or not message_id.strip()
        ):

            raise ValueError(
                "message_id is required."
            )

        message_id = (
            message_id.strip()
        )

        # =====================================================
        # Validate Body
        # =====================================================

        if (
            not body
            or not body.strip()
        ):

            raise ValueError(
                "Reply body is required."
            )

        # =====================================================
        # Get Gmail Service
        # =====================================================

        try:

            service = (
                self.gmail_client.get_service(
                    account_email
                )
            )

        except Exception as exc:

            print("=" * 70)
            print(
                "GMAIL SERVICE INITIALIZATION FAILED"
            )
            print(
                "Account:",
                account_email,
            )
            print(
                "Exception type:",
                type(exc).__name__,
            )
            print(
                "Exception:",
                str(exc),
            )
            print("=" * 70)

            raise RuntimeError(
                "Unable to initialize Gmail service."
            ) from exc

        # =====================================================
        # Retrieve Original Gmail Message
        # =====================================================

        try:

            original_message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=[
                        "From",
                        "To",
                        "Cc",
                        "Subject",
                        "Message-ID",
                        "References",
                        "Reply-To",
                    ],
                )
                .execute()
            )

        except HttpError as exc:

            print("=" * 70)
            print(
                "GMAIL ORIGINAL MESSAGE RETRIEVAL FAILED"
            )
            print(
                "Account:",
                account_email,
            )
            print(
                "Message ID:",
                message_id,
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
                "Unable to retrieve original Gmail message."
            ) from exc

        except Exception as exc:

            print("=" * 70)
            print(
                "GMAIL ORIGINAL MESSAGE RETRIEVAL FAILED"
            )
            print(
                "Account:",
                account_email,
            )
            print(
                "Message ID:",
                message_id,
            )
            print(
                "Exception type:",
                type(exc).__name__,
            )
            print(
                "Exception:",
                str(exc),
            )
            print("=" * 70)

            raise RuntimeError(
                "Unable to retrieve original Gmail message."
            ) from exc

        # =====================================================
        # Extract Payload
        # =====================================================

        payload = (
            original_message.get(
                "payload",
                {},
            )
            or {}
        )

        headers = (
            payload.get(
                "headers",
                [],
            )
            or []
        )

        if not isinstance(
            headers,
            list,
        ):

            headers = []

        # =====================================================
        # Determine Recipient Dynamically
        # =====================================================

        try:

            recipient = (
                self._determine_reply_recipient(
                    headers=headers,
                    account_email=account_email,
                )
            )

        except ValueError as exc:

            raise RuntimeError(
                str(exc)
            ) from exc

        # =====================================================
        # Original Message-ID
        # =====================================================

        original_message_id = (
            self._get_header(
                headers,
                "Message-ID",
            )
        )

        # =====================================================
        # Build References
        # =====================================================

        references = (
            self._build_references(
                headers=headers,
                message_id=original_message_id,
            )
        )

        # =====================================================
        # Existing Thread ID
        # =====================================================

        thread_id = (
            original_message.get(
                "threadId"
            )
        )

        if not thread_id:

            raise RuntimeError(
                "Original Gmail message does not contain "
                "a thread ID."
            )

        # =====================================================
        # Build Final Email Body
        # =====================================================

        final_body = (
            self._apply_email_footer(
                body
            )
        )

        # =====================================================
        # Safety Check
        # =====================================================

        if "\\n" in final_body:

            print("=" * 70)
            print(
                "LITERAL ESCAPED NEWLINE DETECTED"
            )
            print(
                "Normalizing final email body."
            )
            print("=" * 70)

            final_body = (
                final_body.replace(
                    "\\r\\n",
                    "\n",
                )
                .replace(
                    "\\n",
                    "\n",
                )
                .replace(
                    "\\r",
                    "\n",
                )
            )

        # =====================================================
        # Debug Final Body
        # =====================================================

        print("=" * 70)
        print(
            "FINAL REPLY BODY BEFORE MIME ENCODING"
        )
        print("=" * 70)

        print(
            "RAW REPRESENTATION:"
        )

        print(
            repr(final_body)
        )

        print("-" * 70)

        print(
            "VISIBLE BODY:"
        )

        print(
            final_body
        )

        print("-" * 70)

        print(
            "Contains literal \\\\n:",
            "\\n" in final_body,
        )

        print(
            "Contains actual newline:",
            "\n" in final_body,
        )

        print("=" * 70)

        # =====================================================
        # Build MIME Message
        # =====================================================

        mime_message = MIMEText(
            final_body,
            "plain",
            "utf-8",
        )

        # =====================================================
        # To
        # =====================================================

        mime_message["To"] = recipient

        # =====================================================
        # Subject
        # =====================================================

        subject = self._get_header(
            headers,
            "Subject",
        )

        if subject:

            subject = (
                subject.strip()
            )

            if subject.lower().startswith(
                "re:"
            ):

                mime_message["Subject"] = (
                    subject
                )

            else:

                mime_message["Subject"] = (
                    f"Re: {subject}"
                )

        # =====================================================
        # In-Reply-To
        # =====================================================

        if original_message_id:

            mime_message["In-Reply-To"] = (
                original_message_id
            )

        # =====================================================
        # References
        # =====================================================

        if references:

            mime_message["References"] = (
                references
            )

        # =====================================================
        # Encode MIME
        # =====================================================

        raw_message = (
            urlsafe_b64encode(
                mime_message.as_bytes()
            )
            .decode("utf-8")
        )

        # =====================================================
        # Send Gmail Reply
        # =====================================================

        try:

            sent_message = (
                service.users()
                .messages()
                .send(
                    userId="me",
                    body={
                        "raw": raw_message,
                        "threadId": thread_id,
                    },
                )
                .execute()
            )

        except HttpError as exc:

            print("=" * 70)
            print(
                "GMAIL REPLY FAILED"
            )
            print(
                "Account:",
                account_email,
            )
            print(
                "Recipient:",
                recipient,
            )
            print(
                "Thread ID:",
                thread_id,
            )
            print(
                "Message ID:",
                message_id,
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
                "Unable to send Gmail reply."
            ) from exc

        except Exception as exc:

            print("=" * 70)
            print(
                "GMAIL REPLY FAILED"
            )
            print(
                "Account:",
                account_email,
            )
            print(
                "Recipient:",
                recipient,
            )
            print(
                "Thread ID:",
                thread_id,
            )
            print(
                "Message ID:",
                message_id,
            )
            print(
                "Exception type:",
                type(exc).__name__,
            )
            print(
                "Exception:",
                str(exc),
            )
            print("=" * 70)

            raise RuntimeError(
                "Unable to send Gmail reply."
            ) from exc

        # =====================================================
        # Gmail Response
        # =====================================================

        sent_message_id = (
            sent_message.get(
                "id"
            )
        )

        sent_thread_id = (
            sent_message.get(
                "threadId"
            )
            or thread_id
        )

        print("=" * 70)
        print(
            "GMAIL REPLY SENT SUCCESSFULLY"
        )
        print("=" * 70)
        print(
            "Account:",
            account_email,
        )
        print(
            "Recipient:",
            recipient,
        )
        print(
            "Original Message ID:",
            message_id,
        )
        print(
            "Reply Message ID:",
            sent_message_id,
        )
        print(
            "Thread ID:",
            sent_thread_id,
        )
        print("=" * 70)

        return {
            "success": True,
            "message_id": sent_message_id,
            "thread_id": sent_thread_id,
            "recipient": recipient,
            "subject": subject,
            "status": "sent",
        }


# =============================================================
# Shared Gmail Reply Service
# =============================================================

gmail_reply_service = GmailReplyService()