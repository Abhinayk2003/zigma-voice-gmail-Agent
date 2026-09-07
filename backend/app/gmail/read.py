from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from app.gmail.client import GmailClient


class GmailReadService:
    """
    Gmail read and message-management service.

    Responsibilities:

        - List Gmail messages
        - Retrieve individual messages
        - Retrieve complete threads
        - Extract message metadata
        - Extract plain-text / HTML bodies
        - Extract attachment metadata
        - Search Gmail
        - List unread messages
        - List today's messages
        - Mark messages as read/unread
        - Star/unstar messages
        - Move messages to Trash

    Design principles:

        - Account email is always supplied by the authenticated caller.
        - Message IDs are always supplied by Gmail or ConversationState.
        - Thread IDs are always supplied by Gmail or ConversationState.
        - Search queries are supplied dynamically.
        - Result limits are supplied dynamically.
        - No user-specific Gmail information is hard-coded.

    Gmail API constants such as "me", "UNREAD", "STARRED"
    and "is:unread" are API-defined values and are not
    user/business data.
    """

    # =========================================================
    # Gmail API constants
    # =========================================================

    GMAIL_USER = "me"

    LABEL_UNREAD = "UNREAD"
    LABEL_STARRED = "STARRED"

    QUERY_UNREAD = "is:unread"

    # Default timezone used only when calculating
    # calendar-day based Gmail queries.
    #
    # This can be overridden through the constructor.
    DEFAULT_TIMEZONE = "Asia/Kolkata"

    # =========================================================
    # Initialization
    # =========================================================

    def __init__(
        self,
        gmail_client: GmailClient | None = None,
        timezone_name: str | None = None,
    ) -> None:

        self.gmail_client = (
            gmail_client
            or GmailClient()
        )

        self.timezone_name = (
            timezone_name
            or self.DEFAULT_TIMEZONE
        )

    # =========================================================
    # Validation helpers
    # =========================================================

    @staticmethod
    def _validate_account(
        account_email: str | None,
    ) -> str:
        """
        Validate and normalize the authenticated Gmail account.
        """

        if not account_email:
            raise ValueError(
                "Authenticated Gmail account is required."
            )

        account = str(
            account_email
        ).strip()

        if not account:
            raise ValueError(
                "Authenticated Gmail account is required."
            )

        return account

    @staticmethod
    def _validate_message_id(
        message_id: str | None,
    ) -> str:
        """
        Validate and normalize a Gmail message ID.
        """

        if not message_id:
            raise ValueError(
                "message_id is required."
            )

        normalized = str(
            message_id
        ).strip()

        if not normalized:
            raise ValueError(
                "message_id is required."
            )

        return normalized

    @staticmethod
    def _validate_thread_id(
        thread_id: str | None,
    ) -> str:
        """
        Validate and normalize a Gmail thread ID.
        """

        if not thread_id:
            raise ValueError(
                "thread_id is required."
            )

        normalized = str(
            thread_id
        ).strip()

        if not normalized:
            raise ValueError(
                "thread_id is required."
            )

        return normalized

    @staticmethod
    def _validate_max_results(
        max_results: int | None,
    ) -> int | None:
        """
        Validate an optional Gmail result limit.
        """

        if max_results is None:
            return None

        if isinstance(
            max_results,
            bool,
        ):
            raise ValueError(
                "max_results must be an integer greater than zero."
            )

        if max_results <= 0:
            raise ValueError(
                "max_results must be greater than zero."
            )

        return int(
            max_results
        )

    @staticmethod
    def _normalize_page_token(
        page_token: str | None,
    ) -> str | None:
        """
        Normalize an optional Gmail pagination token.
        """

        if page_token is None:
            return None

        token = str(
            page_token
        ).strip()

        return token or None

    # =========================================================
    # Header helper
    # =========================================================

    @staticmethod
    def _get_header(
        headers: list[dict[str, Any]],
        name: str,
    ) -> str | None:
        """
        Retrieve a Gmail header value case-insensitively.
        """

        target_name = name.strip().lower()

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

            if header_name != target_name:
                continue

            value = header.get(
                "value"
            )

            if value is not None:
                return str(
                    value
                )

        return None

    # =========================================================
    # Decode Gmail body
    # =========================================================

    @staticmethod
    def _decode_body(
        data: str | None,
    ) -> str:
        """
        Decode Gmail URL-safe Base64 message data.
        """

        if not data:
            return ""

        try:

            decoded = (
                base64.urlsafe_b64decode(
                    data.encode("utf-8")
                )
            )

            return decoded.decode(
                "utf-8",
                errors="replace",
            )

        except (
            ValueError,
            TypeError,
            base64.binascii.Error,
        ):
            return ""

    # =========================================================
    # Extract MIME content
    # =========================================================

    @classmethod
    def _extract_content(
        cls,
        payload: dict[str, Any],
    ) -> tuple[
        str,
        str,
        list[dict[str, Any]],
    ]:
        """
        Recursively process Gmail MIME parts.

        Returns:

            plain_text
            html
            attachments
        """

        plain_text_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[dict[str, Any]] = []

        def process_part(
            part: dict[str, Any],
        ) -> None:

            if not isinstance(
                part,
                dict,
            ):
                return

            mime_type = str(
                part.get(
                    "mimeType",
                    "",
                )
            ).strip().lower()

            filename = str(
                part.get(
                    "filename",
                    "",
                )
                or ""
            ).strip()

            body = (
                part.get(
                    "body",
                    {},
                )
                or {}
            )

            if not isinstance(
                body,
                dict,
            ):
                body = {}

            attachment_id = body.get(
                "attachmentId"
            )

            data = body.get(
                "data"
            )

            # -------------------------------------------------
            # Attachment
            # -------------------------------------------------

            if filename:

                attachments.append(
                    {
                        "filename": filename,

                        "mime_type": mime_type,

                        "size": body.get(
                            "size",
                            0,
                        ),

                        "attachment_id": (
                            attachment_id
                        ),
                    }
                )

            # -------------------------------------------------
            # Plain text
            # -------------------------------------------------

            elif (
                mime_type == "text/plain"
                and data
            ):

                text = cls._decode_body(
                    data
                )

                if text.strip():

                    plain_text_parts.append(
                        text
                    )

            # -------------------------------------------------
            # HTML
            # -------------------------------------------------

            elif (
                mime_type == "text/html"
                and data
            ):

                html = cls._decode_body(
                    data
                )

                if html.strip():

                    html_parts.append(
                        html
                    )

            # -------------------------------------------------
            # Nested MIME parts
            # -------------------------------------------------

            children = (
                part.get(
                    "parts",
                    [],
                )
                or []
            )

            if not isinstance(
                children,
                list,
            ):
                return

            for child in children:

                if isinstance(
                    child,
                    dict,
                ):
                    process_part(
                        child
                    )

        if isinstance(
            payload,
            dict,
        ):
            process_part(
                payload
            )

        plain_text = "\n".join(
            part.strip()
            for part in plain_text_parts
            if part.strip()
        )

        html = "\n".join(
            part.strip()
            for part in html_parts
            if part.strip()
        )

        return (
            plain_text,
            html,
            attachments,
        )

    # =========================================================
    # Parse Gmail message
    # =========================================================

    @classmethod
    def _parse_message(
        cls,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Convert Gmail API message data into application-level data.
        """

        payload = (
            message.get(
                "payload",
                {},
            )
            or {}
        )

        if not isinstance(
            payload,
            dict,
        ):
            payload = {}

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

        body, body_html, attachments = (
            cls._extract_content(
                payload
            )
        )

        return {
            # Gmail-generated identifiers
            "id": message.get(
                "id"
            ),

            "thread_id": message.get(
                "threadId"
            ),

            # Gmail metadata
            "label_ids": message.get(
                "labelIds",
                [],
            ),

            "snippet": message.get(
                "snippet",
                "",
            ),

            "internal_date": message.get(
                "internalDate"
            ),

            # Email headers
            "from": cls._get_header(
                headers,
                "From",
            ),

            "to": cls._get_header(
                headers,
                "To",
            ),

            "cc": cls._get_header(
                headers,
                "Cc",
            ),

            "bcc": cls._get_header(
                headers,
                "Bcc",
            ),

            "reply_to": cls._get_header(
                headers,
                "Reply-To",
            ),

            "subject": cls._get_header(
                headers,
                "Subject",
            ),

            "date": cls._get_header(
                headers,
                "Date",
            ),

            "message_id": cls._get_header(
                headers,
                "Message-ID",
            ),

            "references": cls._get_header(
                headers,
                "References",
            ),

            # Extracted content
            "body": body,

            "body_html": body_html,

            "attachments": attachments,
        }

    # =========================================================
    # List messages
    # =========================================================

    def list_messages(
        self,
        account_email: str,
        query: str | None = None,
        max_results: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve Gmail messages dynamically.

        The caller supplies:

            account_email
            optional query
            optional result limit
            optional page token

        Gmail supplies:

            message IDs
            thread IDs
            message metadata
        """

        account = self._validate_account(
            account_email
        )

        validated_max_results = (
            self._validate_max_results(
                max_results
            )
        )

        normalized_page_token = (
            self._normalize_page_token(
                page_token
            )
        )

        service = self.gmail_client.get_service(
            account
        )

        request_params: dict[str, Any] = {
            "userId": self.GMAIL_USER,
        }

        # -----------------------------------------------------
        # Dynamic Gmail query
        # -----------------------------------------------------

        if query is not None:

            cleaned_query = str(
                query
            ).strip()

            if cleaned_query:

                request_params["q"] = (
                    cleaned_query
                )

        # -----------------------------------------------------
        # Dynamic result limit
        # -----------------------------------------------------

        if validated_max_results is not None:

            request_params[
                "maxResults"
            ] = validated_max_results

        # -----------------------------------------------------
        # Dynamic pagination
        # -----------------------------------------------------

        if normalized_page_token:

            request_params[
                "pageToken"
            ] = normalized_page_token

        try:

            response = (
                service.users()
                .messages()
                .list(
                    **request_params
                )
                .execute()
            )

        except HttpError as exc:

            print("=" * 70)
            print(
                "GMAIL MESSAGE LIST FAILED"
            )
            print(
                "Account:",
                account,
            )
            print(
                "Query:",
                query,
            )
            print(
                "Max Results:",
                validated_max_results,
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
                "Unable to retrieve Gmail messages."
            ) from exc

        message_refs = (
            response.get(
                "messages",
                [],
            )
            or []
        )

        if not isinstance(
            message_refs,
            list,
        ):
            message_refs = []

        messages: list[
            dict[str, Any]
        ] = []

        # -----------------------------------------------------
        # Gmail messages.list() returns references.
        #
        # Fetch each message dynamically using the Gmail-
        # supplied message ID.
        # -----------------------------------------------------

        for message_ref in message_refs:

            if not isinstance(
                message_ref,
                dict,
            ):
                continue

            message_id = message_ref.get(
                "id"
            )

            if not message_id:
                continue

            try:

                message = (
                    service.users()
                    .messages()
                    .get(
                        userId=self.GMAIL_USER,
                        id=message_id,
                        format="full",
                    )
                    .execute()
                )

                if isinstance(
                    message,
                    dict,
                ):

                    messages.append(
                        self._parse_message(
                            message
                        )
                    )

            except HttpError as exc:

                print(
                    "Unable to retrieve message:",
                    message_id,
                    type(exc).__name__,
                )

        return {
            "messages": messages,

            "count": len(
                messages
            ),

            "next_page_token": response.get(
                "nextPageToken"
            ),

            "result_size_estimate": response.get(
                "resultSizeEstimate"
            ),
        }

    # =========================================================
    # Get one message
    # =========================================================

    def get_message(
        self,
        account_email: str,
        message_id: str,
        format: str = "full",
    ) -> dict[str, Any]:
        """
        Retrieve one Gmail message.

        The message ID must come from Gmail/ConversationState.
        """

        account = self._validate_account(
            account_email
        )

        normalized_message_id = (
            self._validate_message_id(
                message_id
            )
        )

        allowed_formats = {
            "minimal",
            "metadata",
            "full",
            "raw",
        }

        requested_format = (
            str(format).strip().lower()
            if format
            else "full"
        )

        if requested_format not in allowed_formats:

            raise ValueError(
                "Invalid Gmail message format. "
                f"Allowed values: "
                f"{sorted(allowed_formats)}"
            )

        service = self.gmail_client.get_service(
            account
        )

        try:

            message = (
                service.users()
                .messages()
                .get(
                    userId=self.GMAIL_USER,
                    id=normalized_message_id,
                    format=requested_format,
                )
                .execute()
            )

        except HttpError as exc:

            print("=" * 70)
            print(
                "GMAIL API MESSAGE ERROR"
            )
            print(
                "Message ID:",
                normalized_message_id,
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
                "Error:",
                str(exc),
            )
            print("=" * 70)

            raise RuntimeError(
                "Unable to retrieve Gmail message."
            ) from exc

        if requested_format in {
            "metadata",
            "full",
        }:

            return self._parse_message(
                message
            )

        return message

    # =========================================================
    # Get thread
    # =========================================================

    def get_thread(
        self,
        account_email: str,
        thread_id: str,
    ) -> dict[str, Any]:
        """
        Retrieve an entire Gmail conversation.

        The thread ID must come from Gmail/ConversationState.
        """

        account = self._validate_account(
            account_email
        )

        normalized_thread_id = (
            self._validate_thread_id(
                thread_id
            )
        )

        service = self.gmail_client.get_service(
            account
        )

        try:

            thread = (
                service.users()
                .threads()
                .get(
                    userId=self.GMAIL_USER,
                    id=normalized_thread_id,
                    format="full",
                )
                .execute()
            )

        except HttpError as exc:

            print("=" * 70)
            print(
                "GMAIL API THREAD ERROR"
            )
            print(
                "Thread ID:",
                normalized_thread_id,
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
                "Error:",
                str(exc),
            )
            print("=" * 70)

            raise RuntimeError(
                "Unable to retrieve Gmail thread."
            ) from exc

        raw_messages = (
            thread.get(
                "messages",
                [],
            )
            or []
        )

        if not isinstance(
            raw_messages,
            list,
        ):
            raw_messages = []

        messages = [
            self._parse_message(
                message
            )
            for message in raw_messages
            if isinstance(
                message,
                dict,
            )
        ]

        return {
            "id": thread.get(
                "id"
            ),

            "history_id": thread.get(
                "historyId"
            ),

            "messages": messages,

            "message_count": len(
                messages
            ),
        }

    # =========================================================
    # Modify labels
    # =========================================================

    def _modify_labels(
        self,
        account_email: str,
        message_id: str,
        *,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        operation_name: str,
        status: str,
    ) -> dict[str, Any]:
        """
        Centralized Gmail label modification.

        Used for:

            - Mark read
            - Mark unread
            - Star
            - Unstar
        """

        account = self._validate_account(
            account_email
        )

        normalized_message_id = (
            self._validate_message_id(
                message_id
            )
        )

        body: dict[str, Any] = {}

        if add_labels:

            body["addLabelIds"] = list(
                add_labels
            )

        if remove_labels:

            body["removeLabelIds"] = list(
                remove_labels
            )

        if not body:

            raise ValueError(
                "At least one label modification is required."
            )

        service = self.gmail_client.get_service(
            account
        )

        try:

            response = (
                service.users()
                .messages()
                .modify(
                    userId=self.GMAIL_USER,
                    id=normalized_message_id,
                    body=body,
                )
                .execute()
            )

        except HttpError as exc:

            print("=" * 70)
            print(
                f"GMAIL {operation_name.upper()} FAILED"
            )
            print(
                "Message ID:",
                normalized_message_id,
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
                f"Unable to {operation_name}."
            ) from exc

        return {
            "message_id": response.get(
                "id",
                normalized_message_id,
            ),

            "thread_id": response.get(
                "threadId"
            ),

            "label_ids": response.get(
                "labelIds",
                [],
            ),

            "status": status,
        }

    # =========================================================
    # Mark as read
    # =========================================================

    def mark_as_read(
        self,
        account_email: str,
        message_id: str,
    ) -> dict[str, Any]:

        return self._modify_labels(
            account_email=account_email,
            message_id=message_id,
            remove_labels=[
                self.LABEL_UNREAD
            ],
            operation_name=(
                "mark Gmail message as read"
            ),
            status="read",
        )

    # =========================================================
    # Mark as unread
    # =========================================================

    def mark_as_unread(
        self,
        account_email: str,
        message_id: str,
    ) -> dict[str, Any]:

        return self._modify_labels(
            account_email=account_email,
            message_id=message_id,
            add_labels=[
                self.LABEL_UNREAD
            ],
            operation_name=(
                "mark Gmail message as unread"
            ),
            status="unread",
        )

    # =========================================================
    # Star
    # =========================================================

    def star_message(
        self,
        account_email: str,
        message_id: str,
    ) -> dict[str, Any]:

        return self._modify_labels(
            account_email=account_email,
            message_id=message_id,
            add_labels=[
                self.LABEL_STARRED
            ],
            operation_name=(
                "star Gmail message"
            ),
            status="starred",
        )

    # =========================================================
    # Unstar
    # =========================================================

    def unstar_message(
        self,
        account_email: str,
        message_id: str,
    ) -> dict[str, Any]:

        return self._modify_labels(
            account_email=account_email,
            message_id=message_id,
            remove_labels=[
                self.LABEL_STARRED
            ],
            operation_name=(
                "unstar Gmail message"
            ),
            status="unstarred",
        )

    # =========================================================
    # Move to Trash
    # =========================================================

    def delete_message(
        self,
        account_email: str,
        message_id: str,
    ) -> dict[str, Any]:
        """
        Move a Gmail message to Trash.

        This does not permanently delete the message.

        The caller is responsible for confirmation before
        invoking this method.
        """

        account = self._validate_account(
            account_email
        )

        normalized_message_id = (
            self._validate_message_id(
                message_id
            )
        )

        service = self.gmail_client.get_service(
            account
        )

        try:

            response = (
                service.users()
                .messages()
                .trash(
                    userId=self.GMAIL_USER,
                    id=normalized_message_id,
                )
                .execute()
            )

        except HttpError as exc:

            print("=" * 70)
            print(
                "GMAIL DELETE MESSAGE FAILED"
            )
            print(
                "Message ID:",
                normalized_message_id,
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
                "Unable to move Gmail message to Trash."
            ) from exc

        return {
            "message_id": response.get(
                "id",
                normalized_message_id,
            ),

            "thread_id": response.get(
                "threadId"
            ),

            "label_ids": response.get(
                "labelIds",
                [],
            ),

            "status": "trashed",
        }

    # =========================================================
    # Unread emails
    # =========================================================

    def list_unread(
        self,
        account_email: str,
        max_results: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve unread Gmail messages.

        The Gmail query itself is a Gmail system operator,
        not user-specific data.
        """

        return self.list_messages(
            account_email=account_email,
            query=self.QUERY_UNREAD,
            max_results=max_results,
            page_token=page_token,
        )

    # =========================================================
    # Today's emails
    # =========================================================

    def list_today(
        self,
        account_email: str,
        max_results: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve emails received during the current calendar day.

        The date range is generated dynamically at runtime.

        The timezone is configurable through the service instance.
        """

        try:

            timezone = ZoneInfo(
                self.timezone_name
            )

        except Exception as exc:

            raise ValueError(
                "Invalid Gmail service timezone: "
                f"{self.timezone_name}"
            ) from exc

        now = datetime.now(
            timezone
        )

        today = now.date()

        tomorrow = (
            today
            + timedelta(days=1)
        )

        query = (
            f"after:{today:%Y/%m/%d} "
            f"before:{tomorrow:%Y/%m/%d}"
        )

        return self.list_messages(
            account_email=account_email,
            query=query,
            max_results=max_results,
            page_token=page_token,
        )

    # =========================================================
    # Search
    # =========================================================

    def search(
        self,
        account_email: str,
        query: str,
        max_results: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a dynamic Gmail search.

        The complete Gmail search query is supplied at runtime.

        Examples of possible runtime queries include:

            from:<dynamic sender>
            to:<dynamic recipient>
            subject:<dynamic subject>
            is:unread
            after:<dynamic date>
            before:<dynamic date>

        No user-specific search information is hard-coded.
        """

        if query is None:

            raise ValueError(
                "Gmail search query is required."
            )

        cleaned_query = str(
            query
        ).strip()

        if not cleaned_query:

            raise ValueError(
                "Gmail search query is required."
            )

        return self.list_messages(
            account_email=account_email,
            query=cleaned_query,
            max_results=max_results,
            page_token=page_token,
        )


# =============================================================
# Shared service instance
# =============================================================

gmail_read_service = GmailReadService()