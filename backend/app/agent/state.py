from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =============================================================
# Gmail Result
# =============================================================


@dataclass
class GmailResult:
    """
    Represents one Gmail message in the conversation context.

    The position is temporary and belongs only to the current
    Gmail result set.

    IMPORTANT:

    message_id and thread_id are ALWAYS obtained dynamically
    from Gmail.

    Nothing here is hard-coded.
    """

    position: int

    message_id: str

    thread_id: str | None = None

    subject: str | None = None

    sender: str | None = None

    recipient: str | None = None

    snippet: str | None = None

    date: str | None = None

    data: dict[str, Any] = field(
        default_factory=dict
    )


# =============================================================
# Conversation State
# =============================================================


class ConversationState:
    """
    Dynamic conversation memory for the Gmail agent.

    This class does NOT hard-code:

        - Gmail account
        - Gmail message IDs
        - Gmail thread IDs
        - senders
        - recipients
        - subjects
        - message positions
        - message bodies

    All Gmail identifiers come from Gmail itself.

    The state remembers enough context to understand natural
    follow-up requests such as:

        "the third email"
        "the second one"
        "that email"
        "this email"
        "the previous email"
        "the latest email"
        "same mail"
        "same email"
        "same message"
        "same thread"
        "the email I just sent"
        "the email I just replied to"

    It also remembers the last successful SEND and REPLY
    operations so that a newly created Gmail message can still
    be referenced even when it is not present in the current
    search results.
    """

    def __init__(
        self,
        account_email: str | None = None,
    ) -> None:

        # =====================================================
        # Authenticated account
        # =====================================================

        self.account_email = account_email

        # =====================================================
        # Current user request
        # =====================================================

        self.current_query: str | None = None

        # =====================================================
        # Current Gmail search results
        # =====================================================

        self.current_results: list[GmailResult] = []

        # =====================================================
        # Current selected Gmail message
        # =====================================================

        self.selected_message_id: str | None = None

        self.selected_thread_id: str | None = None

        # =====================================================
        # Previous selected Gmail message
        # =====================================================

        self.previous_message_id: str | None = None

        self.previous_thread_id: str | None = None

        # =====================================================
        # Current conversational Gmail context
        #
        # This is different from current_results.
        #
        # Example:
        #
        # User:
        #   Send email to someone...
        #
        # Gmail:
        #   message_id = dynamically returned
        #   thread_id  = dynamically returned
        #
        # That message may NOT exist inside current_results.
        #
        # We therefore remember it separately.
        # =====================================================

        self.current_message_context: (
            dict[str, Any] | None
        ) = None

        # =====================================================
        # Previous conversational Gmail context
        # =====================================================

        self.previous_message_context: (
            dict[str, Any] | None
        ) = None

        # =====================================================
        # Last sent message
        # =====================================================

        self.last_sent_message: (
            dict[str, Any] | None
        ) = None

        # =====================================================
        # Last replied message
        # =====================================================

        self.last_replied_message: (
            dict[str, Any] | None
        ) = None

        # =====================================================
        # Last successful Gmail operation
        # =====================================================

        self.last_gmail_operation: (
            dict[str, Any] | None
        ) = None

        # =====================================================
        # Last completed application action
        # =====================================================

        self.last_action: str | None = None

        # =====================================================
        # Conversation history
        #
        # This stores the interaction/action history for the
        # current in-memory session.
        # =====================================================

        self.history: list[
            dict[str, Any]
        ] = []

        # =====================================================
        # Gmail pagination
        # =====================================================

        self.next_page_token: str | None = None

        self.current_page: int = 1

        # =====================================================
        # Pending conversational/destructive action
        #
        # Example:
        #
        # {
        #     "action": "delete",
        #     "message_id": "...",
        #     "thread_id": "...",
        #     "account_email": "...",
        #     ...
        # }
        #
        # IDs are always obtained from Gmail/state.
        # =====================================================

        self.pending_action: (
            dict[str, Any] | None
        ) = None

    # =========================================================
    # Account
    # =========================================================

    def set_account(
        self,
        account_email: str,
    ) -> None:
        """
        Set the authenticated Gmail account.

        The account comes from authentication.

        The LLM never controls the account identity.
        """

        if not account_email:
            raise ValueError(
                "account_email is required."
            )

        cleaned = (
            str(account_email)
            .strip()
            .lower()
        )

        if not cleaned:
            raise ValueError(
                "account_email cannot be empty."
            )

        self.account_email = cleaned

    # =========================================================
    # Gmail Result Set
    # =========================================================

    def set_results(
        self,
        messages: list[dict[str, Any]],
        query: str | None = None,
        next_page_token: str | None = None,
    ) -> None:
        """
        Store the latest Gmail result set.

        Positions are generated dynamically from Gmail's
        returned ordering.

        Example:

            Gmail returns:

                message A
                message B
                message C

            State stores:

                1 -> A
                2 -> B
                3 -> C

        No position is hard-coded.
        """

        self.current_results.clear()

        for message in messages:

            if not isinstance(
                message,
                dict,
            ):
                continue

            message_id = message.get(
                "id"
            )

            if not message_id:
                continue

            result = GmailResult(
                position=(
                    len(
                        self.current_results
                    )
                    + 1
                ),

                message_id=str(
                    message_id
                ),

                thread_id=(
                    str(
                        message.get(
                            "thread_id"
                        )
                    )
                    if message.get(
                        "thread_id"
                    )
                    else None
                ),

                subject=message.get(
                    "subject"
                ),

                sender=message.get(
                    "from"
                ),

                recipient=message.get(
                    "to"
                ),

                snippet=message.get(
                    "snippet"
                ),

                date=message.get(
                    "date"
                ),

                data=dict(
                    message
                ),
            )

            self.current_results.append(
                result
            )

        self.current_query = query

        self.next_page_token = (
            next_page_token
        )

        self.current_page = 1

        # -----------------------------------------------------
        # A new search changes the result set.
        #
        # It is safe to clear pending destructive actions
        # because they should not accidentally operate on a
        # newly searched message.
        #
        # IMPORTANT:
        #
        # We DO NOT clear current_message_context.
        #
        # The user may still say:
        #
        #     "Reply to the same email"
        #
        # after another operation.
        # -----------------------------------------------------

        self.clear_pending_action()

    # =========================================================
    # Result Count
    # =========================================================

    def result_count(
        self,
    ) -> int:
        """
        Return the number of current Gmail results.
        """

        return len(
            self.current_results
        )

    # =========================================================
    # Get Result By Position
    # =========================================================

    def get_result(
        self,
        position: int,
    ) -> GmailResult:
        """
        Resolve a numbered Gmail result.

        Example:

            position=3

        returns the third result from Gmail.
        """

        if not self.current_results:

            raise ValueError(
                "There are no Gmail results "
                "in the current context."
            )

        if position < 1:

            raise ValueError(
                "Email position must be "
                "greater than zero."
            )

        if position > len(
            self.current_results
        ):

            raise ValueError(
                f"Only "
                f"{len(self.current_results)} "
                f"email results are currently "
                f"available."
            )

        return self.current_results[
            position - 1
        ]

    # =========================================================
    # Select Result
    # =========================================================

    def select_result(
        self,
        position: int,
    ) -> GmailResult:
        """
        Select one Gmail result.

        The selected message becomes the current conversational
        Gmail context.
        """

        result = self.get_result(
            position
        )

        # -----------------------------------------------------
        # Move current selection into previous selection
        # -----------------------------------------------------

        if self.selected_message_id:

            self.previous_message_id = (
                self.selected_message_id
            )

            self.previous_thread_id = (
                self.selected_thread_id
            )

        if self.current_message_context:

            self.previous_message_context = (
                dict(
                    self.current_message_context
                )
            )

        # -----------------------------------------------------
        # Select new message
        # -----------------------------------------------------

        self.selected_message_id = (
            result.message_id
        )

        self.selected_thread_id = (
            result.thread_id
        )

        # -----------------------------------------------------
        # Remember complete context
        # -----------------------------------------------------

        self.current_message_context = {
            "message_id": result.message_id,
            "thread_id": result.thread_id,
            "subject": result.subject,
            "sender": result.sender,
            "recipient": result.recipient,
            "snippet": result.snippet,
            "date": result.date,
            "body": self._extract_body(
                result.data
            ),
            "action": "select",
            "data": dict(
                result.data
            ),
        }

        self.last_action = (
            "select_email"
        )

        return result

    # =========================================================
    # Get Selected Result
    # =========================================================

    def get_selected_result(
        self,
    ) -> GmailResult | None:
        """
        Resolve the currently selected Gmail message.

        First searches current_results.

        If the selected message was created by SEND or REPLY
        and is therefore not inside current_results, it rebuilds
        a GmailResult from the remembered conversational context.
        """

        if not self.selected_message_id:
            return None

        # -----------------------------------------------------
        # First: current Gmail search results
        # -----------------------------------------------------

        for result in self.current_results:

            if (
                result.message_id
                == self.selected_message_id
            ):
                return result

        # -----------------------------------------------------
        # Second: conversational memory
        # -----------------------------------------------------

        context = (
            self.current_message_context
        )

        if not context:
            return None

        if (
            context.get(
                "message_id"
            )
            != self.selected_message_id
        ):
            return None

        return GmailResult(
            position=0,

            message_id=str(
                context[
                    "message_id"
                ]
            ),

            thread_id=context.get(
                "thread_id"
            ),

            subject=context.get(
                "subject"
            ),

            sender=context.get(
                "sender"
            ),

            recipient=context.get(
                "recipient"
            ),

            snippet=context.get(
                "snippet"
            ),

            date=context.get(
                "date"
            ),

            data=dict(
                context.get(
                    "data",
                    {},
                )
            ),
        )

    # =========================================================
    # Get Previous Result
    # =========================================================

    def get_previous_result(
        self,
    ) -> GmailResult | None:
        """
        Resolve the previously selected Gmail message.

        Works both with current Gmail search results and
        conversational memory.
        """

        if not self.previous_message_id:
            return None

        # -----------------------------------------------------
        # Search result set
        # -----------------------------------------------------

        for result in self.current_results:

            if (
                result.message_id
                == self.previous_message_id
            ):
                return result

        # -----------------------------------------------------
        # Previous conversational context
        # -----------------------------------------------------

        context = (
            self.previous_message_context
        )

        if not context:
            return None

        if (
            context.get(
                "message_id"
            )
            != self.previous_message_id
        ):
            return None

        return GmailResult(
            position=0,

            message_id=str(
                context[
                    "message_id"
                ]
            ),

            thread_id=context.get(
                "thread_id"
            ),

            subject=context.get(
                "subject"
            ),

            sender=context.get(
                "sender"
            ),

            recipient=context.get(
                "recipient"
            ),

            snippet=context.get(
                "snippet"
            ),

            date=context.get(
                "date"
            ),

            data=dict(
                context.get(
                    "data",
                    {},
                )
            ),
        )

    # =========================================================
    # Get Latest Result
    # =========================================================

    def get_latest_result(
        self,
    ) -> GmailResult | None:
        """
        Return the latest result from the current Gmail search.

        If no current search exists, fall back to the current
        conversational Gmail message.
        """

        if self.current_results:

            return self.current_results[0]

        return self.get_selected_result()

    # =========================================================
    # Remember Gmail Message
    # =========================================================

    def remember_message(
        self,
        *,
        message_id: str | None,
        thread_id: str | None = None,
        subject: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        body: str | None = None,
        snippet: str | None = None,
        date: str | None = None,
        action: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Remember a Gmail message as the current conversational
        context.

        All values are dynamic.

        The message_id and thread_id should come from Gmail.
        """

        if not message_id:
            return

        # -----------------------------------------------------
        # Preserve previous context
        # -----------------------------------------------------

        if self.current_message_context:

            self.previous_message_context = (
                dict(
                    self.current_message_context
                )
            )

            self.previous_message_id = (
                self.current_message_context.get(
                    "message_id"
                )
            )

            self.previous_thread_id = (
                self.current_message_context.get(
                    "thread_id"
                )
            )

        # -----------------------------------------------------
        # Create current context
        # -----------------------------------------------------

        context = {
            "message_id": str(
                message_id
            ),

            "thread_id": (
                str(thread_id)
                if thread_id
                else None
            ),

            "subject": subject,

            "sender": sender,

            "recipient": recipient,

            "body": body,

            "snippet": snippet,

            "date": date,

            "action": action,

            "data": (
                dict(data)
                if isinstance(
                    data,
                    dict,
                )
                else {}
            ),
        }

        self.current_message_context = (
            context
        )

        # -----------------------------------------------------
        # Synchronize selected IDs
        # -----------------------------------------------------

        self.selected_message_id = (
            str(message_id)
        )

        self.selected_thread_id = (
            str(thread_id)
            if thread_id
            else None
        )

    # =========================================================
    # Remember Sent Message
    # =========================================================

    def remember_sent_message(
        self,
        *,
        message_id: str | None,
        thread_id: str | None,
        recipient: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        sender: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Remember a newly sent Gmail message.

        This solves the important case where Gmail returns a
        newly created message ID but that message is not yet
        inside current_results.

        Example:

            User:
                Send email...

            Gmail:
                message_id -> dynamic
                thread_id  -> dynamic

            State:
                last_sent_message
                current_message_context

        Later:

            "Reply to the same email"

        can resolve the message dynamically.
        """

        context = {
            "message_id": (
                str(message_id)
                if message_id
                else None
            ),

            "thread_id": (
                str(thread_id)
                if thread_id
                else None
            ),

            "recipient": recipient,

            "subject": subject,

            "body": body,

            "sender": sender,

            "action": "send",

            "data": (
                dict(data)
                if isinstance(
                    data,
                    dict,
                )
                else {}
            ),
        }

        self.last_sent_message = (
            context
        )

        self.remember_message(
            message_id=message_id,
            thread_id=thread_id,
            subject=subject,
            sender=sender,
            recipient=recipient,
            body=body,
            action="send",
            data=data,
        )

        self.last_gmail_operation = {
            "action": "send",
            "message_id": message_id,
            "thread_id": thread_id,
            "recipient": recipient,
            "subject": subject,
        }

    # =========================================================
    # Remember Replied Message
    # =========================================================

    def remember_replied_message(
        self,
        *,
        original_message_id: str | None,
        reply_message_id: str | None,
        thread_id: str | None,
        recipient: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        sender: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Remember a reply and the Gmail conversation/thread it
        belongs to.

        The IDs come dynamically from Gmail/state.
        """

        current_message_id = (
            reply_message_id
            or original_message_id
        )

        context = {
            "original_message_id": (
                str(original_message_id)
                if original_message_id
                else None
            ),

            "message_id": (
                str(current_message_id)
                if current_message_id
                else None
            ),

            "thread_id": (
                str(thread_id)
                if thread_id
                else None
            ),

            "recipient": recipient,

            "subject": subject,

            "body": body,

            "sender": sender,

            "action": "reply",

            "data": (
                dict(data)
                if isinstance(
                    data,
                    dict,
                )
                else {}
            ),
        }

        self.last_replied_message = (
            context
        )

        self.remember_message(
            message_id=current_message_id,
            thread_id=thread_id,
            subject=subject,
            sender=sender,
            recipient=recipient,
            body=body,
            action="reply",
            data=data,
        )

        self.last_gmail_operation = {
            "action": "reply",
            "original_message_id": (
                original_message_id
            ),
            "reply_message_id": (
                reply_message_id
            ),
            "thread_id": thread_id,
            "recipient": recipient,
        }

    # =========================================================
    # Get Last Sent Message
    # =========================================================

    def get_last_sent_message(
        self,
    ) -> dict[str, Any] | None:
        """
        Return a copy of the last sent message context.
        """

        if not self.last_sent_message:
            return None

        return dict(
            self.last_sent_message
        )

    # =========================================================
    # Get Last Replied Message
    # =========================================================

    def get_last_replied_message(
        self,
    ) -> dict[str, Any] | None:
        """
        Return a copy of the last replied message context.
        """

        if not self.last_replied_message:
            return None

        return dict(
            self.last_replied_message
        )

    # =========================================================
    # Get Current Message Context
    # =========================================================

    def get_current_message_context(
        self,
    ) -> dict[str, Any] | None:
        """
        Return a copy of the current conversational Gmail
        context.
        """

        if not self.current_message_context:
            return None

        return dict(
            self.current_message_context
        )

    # =========================================================
    # Resolve Message Reference
    # =========================================================

    def resolve_message(
        self,
        position: int | None = None,
        reference: str | None = None,
    ) -> GmailResult:
        """
        Resolve a natural-language Gmail message reference.

        Supported examples:

            3
            "3"
            "3rd"
            "third"

            "this"
            "that"
            "it"
            "current"
            "selected"

            "same"
            "same mail"
            "same email"
            "same message"
            "same thread"

            "previous"
            "last"

            "latest"

        The actual Gmail identifiers always come from state/Gmail.
        """

        # -----------------------------------------------------
        # Explicit position
        # -----------------------------------------------------

        if position is not None:

            return self.get_result(
                position
            )

        if not reference:

            selected = (
                self.get_selected_result()
            )

            if selected:
                return selected

            raise ValueError(
                "No Gmail message reference "
                "was provided."
            )

        normalized = (
            str(reference)
            .strip()
            .lower()
        )

        # -----------------------------------------------------
        # Current / same message
        # -----------------------------------------------------

        if normalized in {
            "this",
            "that",
            "it",
            "current",
            "selected",

            "same",
            "same mail",
            "same email",
            "same message",
            "same thread",

            "this mail",
            "that mail",

            "this email",
            "that email",

            "this message",
            "that message",

            "this thread",
            "that thread",

            "the same mail",
            "the same email",
            "the same message",
            "the same thread",

            "the email i just sent",
            "the mail i just sent",
            "the message i just sent",

            "the email i just replied to",
            "the mail i just replied to",
            "the message i just replied to",
        }:

            selected = (
                self.get_selected_result()
            )

            if selected:
                return selected

            raise ValueError(
                "There is no currently selected "
                "Gmail message."
            )

        # -----------------------------------------------------
        # Previous message
        # -----------------------------------------------------

        if normalized in {
            "previous",
            "previous mail",
            "previous email",
            "previous message",
            "previous thread",
            "last",
            "last mail",
            "last email",
            "last message",
            "last thread",
        }:

            previous = (
                self.get_previous_result()
            )

            if previous:
                return previous

            raise ValueError(
                "There is no previous Gmail "
                "message in the current "
                "conversation context."
            )

        # -----------------------------------------------------
        # Latest message
        # -----------------------------------------------------

        if normalized in {
            "latest",
            "latest mail",
            "latest email",
            "latest message",
            "latest thread",
        }:

            latest = (
                self.get_latest_result()
            )

            if latest:
                return latest

            raise ValueError(
                "There is no latest Gmail "
                "message available."
            )

        # -----------------------------------------------------
        # Ordinal words
        # -----------------------------------------------------

        ordinal_words = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "sixth": 6,
            "seventh": 7,
            "eighth": 8,
            "ninth": 9,
            "tenth": 10,
            "eleventh": 11,
            "twelfth": 12,
            "thirteenth": 13,
            "fourteenth": 14,
            "fifteenth": 15,
            "sixteenth": 16,
            "seventeenth": 17,
            "eighteenth": 18,
            "nineteenth": 19,
            "twentieth": 20,
        }

        if normalized in ordinal_words:

            return self.get_result(
                ordinal_words[
                    normalized
                ]
            )

        # -----------------------------------------------------
        # Numeric ordinal
        #
        # Examples:
        #
        # 1st
        # 2nd
        # 3rd
        # 4th
        # -----------------------------------------------------

        numeric = normalized

        for suffix in (
            "st",
            "nd",
            "rd",
            "th",
        ):

            if numeric.endswith(
                suffix
            ):

                numeric = numeric[
                    : -len(suffix)
                ]

                break

        if numeric.isdigit():

            position_value = int(
                numeric
            )

            return self.get_result(
                position_value
            )

        raise ValueError(
            "Unable to resolve Gmail "
            f"message reference: {reference}"
        )

    # =========================================================
    # Pending Delete
    # =========================================================

    def set_pending_delete(
        self,
        result: GmailResult,
        account_email: str,
    ) -> None:
        """
        Store a destructive Gmail action that requires
        confirmation.
        """

        self.pending_action = {
            "action": "delete",

            "message_id": (
                result.message_id
            ),

            "thread_id": (
                result.thread_id
            ),

            "position": (
                result.position
            ),

            "subject": (
                result.subject
            ),

            "sender": (
                result.sender
            ),

            "recipient": (
                result.recipient
            ),

            "account_email": (
                account_email
            ),
        }

        self.last_action = (
            "delete_confirmation_required"
        )

    # =========================================================
    # Pending Action
    # =========================================================

    def has_pending_action(
        self,
    ) -> bool:
        """
        Return True if an action is waiting for confirmation.
        """

        return bool(
            self.pending_action
        )

    # =========================================================

    def get_pending_action(
        self,
    ) -> dict[str, Any] | None:
        """
        Return a copy of the pending action.
        """

        if not self.pending_action:
            return None

        return dict(
            self.pending_action
        )

    # =========================================================

    def clear_pending_action(
        self,
    ) -> None:
        """
        Clear any pending action.
        """

        self.pending_action = None

    # =========================================================
    # Record Action
    # =========================================================

    def record_action(
        self,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Record an application action.

        The history is generic so it can support future agent
        capabilities without changing the state architecture.
        """

        entry = {
            "action": action,

            "details": (
                dict(details)
                if isinstance(
                    details,
                    dict,
                )
                else {}
            ),
        }

        self.history.append(
            entry
        )

        self.last_action = action

    # =========================================================
    # Clear Current Results
    # =========================================================

    def clear_results(
        self,
    ) -> None:
        """
        Clear the current Gmail search results.

        Conversational message memory is intentionally preserved.
        """

        self.current_results.clear()

        self.current_query = None

        self.next_page_token = None

        self.current_page = 1

        self.clear_pending_action()

    # =========================================================
    # Clear Current Selection
    # =========================================================

    def clear_selection(
        self,
    ) -> None:
        """
        Clear current and previous selection.

        This also clears conversational Gmail context.
        """

        self.selected_message_id = None

        self.selected_thread_id = None

        self.previous_message_id = None

        self.previous_thread_id = None

        self.current_message_context = None

        self.previous_message_context = None

    # =========================================================
    # Reset State
    # =========================================================

    def reset(
        self,
    ) -> None:
        """
        Reset conversation memory while preserving the
        authenticated Gmail account.
        """

        account_email = (
            self.account_email
        )

        self.__init__(
            account_email=account_email
        )

    # =========================================================
    # Safe State Serialization
    # =========================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Return a JSON-safe representation of the state.

        This is useful for debugging and API responses.

        Gmail identifiers are included because they are actual
        values returned by Gmail, not generated values.
        """

        return {
            # -------------------------------------------------
            # Account
            # -------------------------------------------------

            "account_email": (
                self.account_email
            ),

            # -------------------------------------------------
            # Current request
            # -------------------------------------------------

            "current_query": (
                self.current_query
            ),

            # -------------------------------------------------
            # Current Gmail results
            # -------------------------------------------------

            "result_count": len(
                self.current_results
            ),

            "current_results": [
                {
                    "position": (
                        result.position
                    ),

                    "message_id": (
                        result.message_id
                    ),

                    "thread_id": (
                        result.thread_id
                    ),

                    "subject": (
                        result.subject
                    ),

                    "sender": (
                        result.sender
                    ),

                    "recipient": (
                        result.recipient
                    ),

                    "snippet": (
                        result.snippet
                    ),

                    "date": (
                        result.date
                    ),
                }

                for result
                in self.current_results
            ],

            # -------------------------------------------------
            # Selected message
            # -------------------------------------------------

            "selected_message_id": (
                self.selected_message_id
            ),

            "selected_thread_id": (
                self.selected_thread_id
            ),

            # -------------------------------------------------
            # Previous message
            # -------------------------------------------------

            "previous_message_id": (
                self.previous_message_id
            ),

            "previous_thread_id": (
                self.previous_thread_id
            ),

            # -------------------------------------------------
            # Conversational Gmail memory
            # -------------------------------------------------

            "current_message_context": (
                dict(
                    self.current_message_context
                )
                if self.current_message_context
                else None
            ),

            "previous_message_context": (
                dict(
                    self.previous_message_context
                )
                if self.previous_message_context
                else None
            ),

            # -------------------------------------------------
            # Last SEND
            # -------------------------------------------------

            "last_sent_message": (
                dict(
                    self.last_sent_message
                )
                if self.last_sent_message
                else None
            ),

            # -------------------------------------------------
            # Last REPLY
            # -------------------------------------------------

            "last_replied_message": (
                dict(
                    self.last_replied_message
                )
                if self.last_replied_message
                else None
            ),

            # -------------------------------------------------
            # Last Gmail operation
            # -------------------------------------------------

            "last_gmail_operation": (
                dict(
                    self.last_gmail_operation
                )
                if self.last_gmail_operation
                else None
            ),

            # -------------------------------------------------
            # Application state
            # -------------------------------------------------

            "last_action": (
                self.last_action
            ),

            "next_page_token": (
                self.next_page_token
            ),

            "current_page": (
                self.current_page
            ),

            # -------------------------------------------------
            # History
            # -------------------------------------------------

            "history_count": len(
                self.history
            ),

            # -------------------------------------------------
            # Pending action
            # -------------------------------------------------

            "pending_action": (
                dict(
                    self.pending_action
                )
                if self.pending_action
                else None
            ),
        }

    # =========================================================
    # Internal Helpers
    # =========================================================

    @staticmethod
    def _extract_body(
        data: dict[str, Any],
    ) -> str | None:
        """
        Extract a body value when Gmail/service data already
        contains one.

        This method does not attempt to invent or reconstruct
        email content.
        """

        if not isinstance(
            data,
            dict,
        ):
            return None

        body = data.get(
            "body"
        )

        if body is None:
            return None

        return str(
            body
        )


# =============================================================
# Shared In-Memory Conversation State
# =============================================================

conversation_state = ConversationState()