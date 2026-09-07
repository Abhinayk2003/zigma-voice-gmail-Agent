from __future__ import annotations

from typing import Any

from app.agent.state import (
    ConversationState,
    GmailResult,
    conversation_state,
)
from app.gmail.read import gmail_read_service
from app.gmail.reply import gmail_reply_service
from app.gmail.send import gmail_send_service


class GmailAgentRouter:
    """
    Dynamic Gmail agent router.

    Responsibilities:
    - Resolve Gmail operations from structured actions.
    - Maintain the shared conversation state.
    - Resolve references such as:
        "3rd mail"
        "10th email"
        "that mail"
        "previous mail"
        "latest mail"
    - Call the existing Gmail services.
    - Store Gmail results and selections in conversation state.

    The router does NOT hardcode:
    - Gmail account
    - message IDs
    - thread IDs
    - senders
    - recipients
    - subjects
    - result positions
    """

    def __init__(
        self,
        state: ConversationState,
    ) -> None:
        self.state = state

    # =========================================================
    # Account
    # =========================================================

    def set_account(
        self,
        account_email: str,
    ) -> None:
        """
        Set the authenticated Gmail account.
        """

        self.state.set_account(
            account_email
        )

    def _require_account(self) -> str:
        """
        Return the authenticated Gmail account.
        """

        account_email = self.state.account_email

        if not account_email:
            raise ValueError(
                "No authenticated Gmail account is available."
            )

        return account_email

    # =========================================================
    # Search Emails
    # =========================================================

    def search_emails(
        self,
        query: str,
        max_results: int | None = 10,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Search Gmail dynamically.

        The returned messages are stored in the shared
        conversation state so that later commands can refer to:

            "the 3rd mail"
            "the 10th mail"
            "that mail"
            "the previous mail"
        """

        account_email = self._require_account()

        if not query or not query.strip():
            raise ValueError(
                "Gmail search query is required."
            )

        query = query.strip()

        result = gmail_read_service.search(
            account_email=account_email,
            query=query,
            max_results=max_results,
            page_token=page_token,
        )

        messages = result.get(
            "messages",
            [],
        )

        self.state.set_results(
            messages=messages,
            query=query,
            next_page_token=result.get(
                "next_page_token"
            ),
        )

        self.state.record_action(
            action="search_emails",
            details={
                "query": query,
                "result_count": len(messages),
            },
        )

        return {
            "success": True,
            "query": query,
            "messages": messages,
            "count": result.get(
                "count",
                len(messages),
            ),
            "next_page_token": result.get(
                "next_page_token"
            ),
        }

    # =========================================================
    # Unread Emails
    # =========================================================

    def list_unread(
        self,
        max_results: int | None = 10,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve unread Gmail messages and store them
        in conversation state.
        """

        account_email = self._require_account()

        result = gmail_read_service.list_unread(
            account_email=account_email,
            max_results=max_results,
            page_token=page_token,
        )

        messages = result.get(
            "messages",
            [],
        )

        self.state.set_results(
            messages=messages,
            query="is:unread",
            next_page_token=result.get(
                "next_page_token"
            ),
        )

        self.state.record_action(
            action="list_unread",
            details={
                "result_count": len(messages),
            },
        )

        return {
            "success": True,
            "messages": messages,
            "count": result.get(
                "count",
                len(messages),
            ),
            "next_page_token": result.get(
                "next_page_token"
            ),
        }

    # =========================================================
    # Today's Emails
    # =========================================================

    def list_today(
        self,
        max_results: int | None = 10,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve recent Gmail messages and store them
        in conversation state.
        """

        account_email = self._require_account()

        result = gmail_read_service.list_today(
            account_email=account_email,
            max_results=max_results,
            page_token=page_token,
        )

        messages = result.get(
            "messages",
            [],
        )

        self.state.set_results(
            messages=messages,
            query="newer_than:1d",
            next_page_token=result.get(
                "next_page_token"
            ),
        )

        self.state.record_action(
            action="list_today",
            details={
                "result_count": len(messages),
            },
        )

        return {
            "success": True,
            "messages": messages,
            "count": result.get(
                "count",
                len(messages),
            ),
            "next_page_token": result.get(
                "next_page_token"
            ),
        }

    # =========================================================
    # Get Single Message
    # =========================================================

    def get_message(
        self,
        message_id: str,
    ) -> dict[str, Any]:
        """
        Retrieve a specific Gmail message.
        """

        account_email = self._require_account()

        if not message_id or not message_id.strip():
            raise ValueError(
                "Gmail message ID is required."
            )

        message_id = message_id.strip()

        result = gmail_read_service.get_message(
            account_email=account_email,
            message_id=message_id,
        )

        resolved_message_id = result.get(
            "id",
            message_id,
        )

        thread_id = result.get(
            "thread_id"
        )

        # Preserve previous selection.
        if (
            self.state.selected_message_id
            and self.state.selected_message_id
            != resolved_message_id
        ):
            self.state.previous_message_id = (
                self.state.selected_message_id
            )

            self.state.previous_thread_id = (
                self.state.selected_thread_id
            )

        self.state.selected_message_id = (
            resolved_message_id
        )

        self.state.selected_thread_id = (
            thread_id
        )

        self.state.record_action(
            action="get_message",
            details={
                "message_id": resolved_message_id,
                "thread_id": thread_id,
            },
        )

        return {
            "success": True,
            "message": result,
        }

    # =========================================================
    # Get Thread
    # =========================================================

    def get_thread(
        self,
        thread_id: str,
    ) -> dict[str, Any]:
        """
        Retrieve a complete Gmail conversation thread.
        """

        account_email = self._require_account()

        if not thread_id or not thread_id.strip():
            raise ValueError(
                "Gmail thread ID is required."
            )

        thread_id = thread_id.strip()

        result = gmail_read_service.get_thread(
            account_email=account_email,
            thread_id=thread_id,
        )

        resolved_thread_id = result.get(
            "id",
            thread_id,
        )

        messages = result.get(
            "messages",
            [],
        )

        # Gmail normally returns the thread messages
        # in conversation order. We keep Gmail's order.
        latest_message_id = None

        if messages:
            latest_message_id = messages[-1].get(
                "id"
            )

        if (
            self.state.selected_thread_id
            and self.state.selected_thread_id
            != resolved_thread_id
        ):
            self.state.previous_thread_id = (
                self.state.selected_thread_id
            )

            self.state.previous_message_id = (
                self.state.selected_message_id
            )

        self.state.selected_thread_id = (
            resolved_thread_id
        )

        if latest_message_id:
            self.state.selected_message_id = (
                latest_message_id
            )

        self.state.record_action(
            action="get_thread",
            details={
                "thread_id": resolved_thread_id,
                "message_count": len(messages),
            },
        )

        return {
            "success": True,
            "thread": result,
        }

    # =========================================================
    # Resolve Message
    # =========================================================

    def resolve_message(
        self,
        position: int | None = None,
        reference: str | None = None,
    ) -> GmailResult:
        """
        Resolve a user-facing message reference to the
        actual Gmail message stored in ConversationState.

        Examples:

            3
            "3rd"
            "third"
            "10th"
            "that mail"
            "previous mail"
            "latest mail"
        """

        return self.state.resolve_message(
            position=position,
            reference=reference,
        )

    # =========================================================
    # Select Message
    # =========================================================

    def select_message(
        self,
        position: int,
    ) -> dict[str, Any]:
        """
        Select one message from the current result set.
        """

        result = self.state.select_result(
            position
        )

        self.state.record_action(
            action="select_message",
            details={
                "position": result.position,
                "message_id": result.message_id,
                "thread_id": result.thread_id,
            },
        )

        return {
            "success": True,
            "selected": {
                "position": result.position,
                "message_id": result.message_id,
                "thread_id": result.thread_id,
                "subject": result.subject,
                "sender": result.sender,
                "recipient": result.recipient,
                "snippet": result.snippet,
                "date": result.date,
            },
        }

    # =========================================================
    # Internal Message Resolver
    # =========================================================

    def _resolve_message(
        self,
        message_id: str | None = None,
        position: int | None = None,
        reference: str | None = None,
    ) -> GmailResult:
        """
        Resolve a message using one of:

        1. Explicit Gmail message ID
        2. Result position
        3. Natural reference

        The router never generates a Gmail message ID.
        """

        if message_id:
            message_id = message_id.strip()

            if not message_id:
                raise ValueError(
                    "Gmail message ID cannot be empty."
                )

            # If this message exists in the current context,
            # return its complete state.
            for result in self.state.current_results:
                if result.message_id == message_id:
                    return result

            # A valid Gmail message may not belong to the
            # current search result set. We still allow it.
            return GmailResult(
                position=0,
                message_id=message_id,
            )

        return self.state.resolve_message(
            position=position,
            reference=reference,
        )

    # =========================================================
    # Mark Read
    # =========================================================

    def mark_as_read(
        self,
        message_id: str | None = None,
        position: int | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """
        Mark a dynamically resolved Gmail message as read.
        """

        account_email = self._require_account()

        result = self._resolve_message(
            message_id=message_id,
            position=position,
            reference=reference,
        )

        response = gmail_read_service.mark_as_read(
            account_email=account_email,
            message_id=result.message_id,
        )

        self.state.selected_message_id = (
            result.message_id
        )

        self.state.selected_thread_id = (
            result.thread_id
        )

        self.state.record_action(
            action="mark_as_read",
            details={
                "message_id": result.message_id,
                "thread_id": result.thread_id,
            },
        )

        return {
            "success": True,
            **response,
        }

    # =========================================================
    # Mark Unread
    # =========================================================

    def mark_as_unread(
        self,
        message_id: str | None = None,
        position: int | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """
        Mark a dynamically resolved Gmail message as unread.
        """

        account_email = self._require_account()

        result = self._resolve_message(
            message_id=message_id,
            position=position,
            reference=reference,
        )

        response = gmail_read_service.mark_as_unread(
            account_email=account_email,
            message_id=result.message_id,
        )

        self.state.selected_message_id = (
            result.message_id
        )

        self.state.selected_thread_id = (
            result.thread_id
        )

        self.state.record_action(
            action="mark_as_unread",
            details={
                "message_id": result.message_id,
                "thread_id": result.thread_id,
            },
        )

        return {
            "success": True,
            **response,
        }

    # =========================================================
    # Star
    # =========================================================

    def star_message(
        self,
        message_id: str | None = None,
        position: int | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """
        Star a dynamically resolved Gmail message.
        """

        account_email = self._require_account()

        result = self._resolve_message(
            message_id=message_id,
            position=position,
            reference=reference,
        )

        response = gmail_read_service.star_message(
            account_email=account_email,
            message_id=result.message_id,
        )

        self.state.selected_message_id = (
            result.message_id
        )

        self.state.selected_thread_id = (
            result.thread_id
        )

        self.state.record_action(
            action="star_message",
            details={
                "message_id": result.message_id,
                "thread_id": result.thread_id,
            },
        )

        return {
            "success": True,
            **response,
        }

    # =========================================================
    # Unstar
    # =========================================================

    def unstar_message(
        self,
        message_id: str | None = None,
        position: int | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """
        Remove the star from a dynamically resolved message.
        """

        account_email = self._require_account()

        result = self._resolve_message(
            message_id=message_id,
            position=position,
            reference=reference,
        )

        response = gmail_read_service.unstar_message(
            account_email=account_email,
            message_id=result.message_id,
        )

        self.state.selected_message_id = (
            result.message_id
        )

        self.state.selected_thread_id = (
            result.thread_id
        )

        self.state.record_action(
            action="unstar_message",
            details={
                "message_id": result.message_id,
                "thread_id": result.thread_id,
            },
        )

        return {
            "success": True,
            **response,
        }

    # =========================================================
    # Delete / Trash
    # =========================================================

    def delete_message(
        self,
        message_id: str | None = None,
        position: int | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """
        Move a dynamically resolved Gmail message to Trash.
        """

        account_email = self._require_account()

        result = self._resolve_message(
            message_id=message_id,
            position=position,
            reference=reference,
        )

        response = gmail_read_service.delete_message(
            account_email=account_email,
            message_id=result.message_id,
        )

        self.state.selected_message_id = (
            result.message_id
        )

        self.state.selected_thread_id = (
            result.thread_id
        )

        self.state.record_action(
            action="delete_message",
            details={
                "message_id": result.message_id,
                "thread_id": result.thread_id,
            },
        )

        return {
            "success": True,
            **response,
        }

    # =========================================================
    # Send Email
    # =========================================================

    def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a new Gmail email.
        """

        account_email = self._require_account()

        response = gmail_send_service.send_email(
            account_email=account_email,
            recipient=recipient,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
        )

        message_id = response.get(
            "message_id"
        )

        thread_id = response.get(
            "thread_id"
        )

        # The newly sent email becomes the current selection.
        if message_id:
            if (
                self.state.selected_message_id
                and self.state.selected_message_id
                != message_id
            ):
                self.state.previous_message_id = (
                    self.state.selected_message_id
                )

                self.state.previous_thread_id = (
                    self.state.selected_thread_id
                )

            self.state.selected_message_id = (
                message_id
            )

            self.state.selected_thread_id = (
                thread_id
            )

        self.state.record_action(
            action="send_email",
            details={
                "message_id": message_id,
                "thread_id": thread_id,
                "recipient": recipient,
                "subject": subject,
            },
        )

        return {
            "success": True,
            **response,
        }

    # =========================================================
    # Reply
    # =========================================================

    def reply_to_message(
        self,
        body: str,
        message_id: str | None = None,
        position: int | None = None,
        reference: str | None = None,
    ) -> dict[str, Any]:
        """
        Reply to a dynamically resolved Gmail message.

        GmailReplyService determines dynamically:
        - original sender
        - original thread ID
        - original subject
        - Message-ID
        - References

        The router only resolves which message the user means.
        """

        account_email = self._require_account()

        if not body or not body.strip():
            raise ValueError(
                "Reply body is required."
            )

        result = self._resolve_message(
            message_id=message_id,
            position=position,
            reference=reference,
        )

        original_message_id = result.message_id

        response = gmail_reply_service.reply_to_message(
            account_email=account_email,
            message_id=original_message_id,
            body=body.strip(),
        )

        reply_message_id = response.get(
            "message_id"
        )

        reply_thread_id = response.get(
            "thread_id",
            result.thread_id,
        )

        # Keep the reply as the current selection.
        if reply_message_id:
            self.state.previous_message_id = (
                original_message_id
            )

            self.state.previous_thread_id = (
                result.thread_id
            )

            self.state.selected_message_id = (
                reply_message_id
            )

            self.state.selected_thread_id = (
                reply_thread_id
            )

        else:
            self.state.selected_message_id = (
                original_message_id
            )

            self.state.selected_thread_id = (
                reply_thread_id
            )

        self.state.record_action(
            action="reply_to_message",
            details={
                "original_message_id": original_message_id,
                "reply_message_id": reply_message_id,
                "thread_id": reply_thread_id,
                "recipient": response.get(
                    "recipient"
                ),
            },
        )

        return {
            "success": True,
            **response,
        }

    # =========================================================
    # Generic Action Dispatcher
    # =========================================================

    def execute(
        self,
        action: str,
        **parameters: Any,
    ) -> dict[str, Any]:
        """
        Execute a supported Gmail action.

        This method will later become the execution interface
        for the LLM intent layer.

        Example:

            execute(
                "reply",
                reference="3rd",
                body="I'll check this."
            )

        The router resolves "3rd" through ConversationState
        and sends the actual Gmail message ID to reply.py.
        """

        if not action or not action.strip():
            raise ValueError(
                "Gmail action is required."
            )

        normalized_action = (
            action.strip()
            .lower()
        )

        action_aliases = {
            # Search
            "search": "search_emails",
            "search_email": "search_emails",
            "search_emails": "search_emails",
            "find": "search_emails",

            # Lists
            "list_unread": "list_unread",
            "unread": "list_unread",
            "list_today": "list_today",
            "today": "list_today",

            # Message
            "get": "get_message",
            "get_email": "get_message",
            "get_message": "get_message",

            # Thread
            "get_thread": "get_thread",
            "thread": "get_thread",

            # Selection
            "select": "select_message",
            "select_message": "select_message",

            # Read state
            "mark_read": "mark_as_read",
            "mark_as_read": "mark_as_read",
            "read": "mark_as_read",

            "mark_unread": "mark_as_unread",
            "mark_as_unread": "mark_as_unread",
            "unread_message": "mark_as_unread",

            # Star
            "star": "star_message",
            "star_message": "star_message",

            "unstar": "unstar_message",
            "unstar_message": "unstar_message",

            # Delete
            "delete": "delete_message",
            "trash": "delete_message",
            "delete_message": "delete_message",

            # Send
            "send": "send_email",
            "send_email": "send_email",

            # Reply
            "reply": "reply_to_message",
            "reply_to": "reply_to_message",
            "reply_to_message": "reply_to_message",
        }

        resolved_action = action_aliases.get(
            normalized_action
        )

        if not resolved_action:
            raise ValueError(
                f"Unsupported Gmail action: '{action}'."
            )

        handler = getattr(
            self,
            resolved_action,
            None,
        )

        if not handler:
            raise RuntimeError(
                f"Gmail action handler is unavailable: "
                f"'{resolved_action}'."
            )

        return handler(
            **parameters
        )


# =============================================================
# Shared Gmail Agent Router
# =============================================================
#
# IMPORTANT:
# ConversationState creates the SINGLE shared state object.
#
# We import that same object from state.py instead of creating
# another ConversationState here.
# =============================================================

gmail_agent_router = GmailAgentRouter(
    state=conversation_state
)
