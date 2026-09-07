from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================
# Canonical Gmail intent
# =============================================================


class GmailIntent(str, Enum):
    SEARCH = "search"
    READ = "read"
    SEND = "send"
    DRAFT = "draft"
    REPLY = "reply"
    STAR = "star"
    UNSTAR = "unstar"
    DELETE = "delete"
    MARK_READ = "mark_read"
    MARK_UNREAD = "mark_unread"
    LIST_UNREAD = "list_unread"
    THREAD = "thread"
    UNKNOWN = "unknown"


# =============================================================
# Message reference type
# =============================================================


class MessageReferenceType(str, Enum):
    POSITION = "position"
    CURRENT = "current"
    PREVIOUS = "previous"
    LATEST = "latest"
    NONE = "none"


# =============================================================
# Message reference
# =============================================================


@dataclass
class MessageReference:
    """
    Semantic reference produced by the AI planner or normalized
    from a natural-language reference.

    This represents WHAT message the user means.

    It does NOT contain or resolve a Gmail message ID.

    Actual Gmail message resolution is handled by the
    application/state/executor layer.
    """

    type: MessageReferenceType = MessageReferenceType.NONE

    position: int | None = None

    raw: str | None = None

    def is_present(self) -> bool:
        return self.type != MessageReferenceType.NONE


# =============================================================
# Gmail intent request
# =============================================================


@dataclass
class GmailIntentRequest:
    """
    Structured request produced by the AI planner.

    Natural-language intent understanding belongs to Bedrock.

    Deterministic application logic such as:

        - Gmail message ID resolution
        - Gmail thread ID resolution
        - conversation references
        - authenticated account handling

    remains outside this class.
    """

    # ---------------------------------------------------------
    # Intent
    # ---------------------------------------------------------

    intent: GmailIntent = GmailIntent.UNKNOWN

    # ---------------------------------------------------------
    # Search
    # ---------------------------------------------------------

    query: str | None = None

    # ---------------------------------------------------------
    # Sender
    # ---------------------------------------------------------

    sender: str | None = None

    # ---------------------------------------------------------
    # Message reference
    # ---------------------------------------------------------

    message_reference: MessageReference = field(
        default_factory=MessageReference
    )

    # ---------------------------------------------------------
    # Email fields
    # ---------------------------------------------------------

    recipient: str | None = None

    subject: str | None = None

    body: str | None = None

    cc: str | None = None

    bcc: str | None = None

    # ---------------------------------------------------------
    # Pagination
    # ---------------------------------------------------------

    page: int | None = None

    max_results: int | None = None

    # ---------------------------------------------------------
    # Thread reference
    # ---------------------------------------------------------

    thread_reference: MessageReference = field(
        default_factory=MessageReference
    )

    # ---------------------------------------------------------
    # Planner metadata
    # ---------------------------------------------------------

    confidence: float = 0.0

    raw_text: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    # =========================================================
    # Helper methods
    # =========================================================

    def requires_message_reference(self) -> bool:
        """
        Return True when the intent operates on an existing
        Gmail message.

        LIST_UNREAD is intentionally excluded because it
        retrieves a collection of unread messages and does
        not target one specific message.
        """

        return self.intent in {
            GmailIntent.READ,
            GmailIntent.REPLY,
            GmailIntent.STAR,
            GmailIntent.UNSTAR,
            GmailIntent.DELETE,
            GmailIntent.MARK_READ,
            GmailIntent.MARK_UNREAD,
        }

    def requires_thread_reference(self) -> bool:
        """
        Return True when the intent operates on a Gmail thread.
        """

        return self.intent == GmailIntent.THREAD

    def is_reply(self) -> bool:
        """
        Return True when this request is a reply.
        """

        return self.intent == GmailIntent.REPLY

    def is_send(self) -> bool:
        """
        Return True when this request sends a new email.
        """

        return self.intent == GmailIntent.SEND

    def is_list_unread(self) -> bool:
        """
        Return True when the request asks for unread emails.
        """

        return self.intent == GmailIntent.LIST_UNREAD

    def has_body(self) -> bool:
        """
        Return True when a non-empty email body exists.
        """

        return bool(
            self.body
            and self.body.strip()
        )

    def has_recipient(self) -> bool:
        """
        Return True when a non-empty recipient exists.
        """

        return bool(
            self.recipient
            and self.recipient.strip()
        )

    def has_subject(self) -> bool:
        """
        Return True when a non-empty subject exists.
        """

        return bool(
            self.subject
            and self.subject.strip()
        )

    def has_sender(self) -> bool:
        """
        Return True when sender information exists.
        """

        return bool(
            self.sender
            and self.sender.strip()
        )

    def has_query(self) -> bool:
        """
        Return True when a non-empty Gmail search query exists.
        """

        return bool(
            self.query
            and self.query.strip()
        )


# =============================================================
# Canonical enum validation
# =============================================================


def normalize_intent(
    value: str | GmailIntent | None,
) -> GmailIntent:
    """
    Validate a canonical intent value.

    Natural-language aliases are intentionally NOT handled here.

    Bedrock is responsible for understanding natural language.
    """

    if isinstance(
        value,
        GmailIntent,
    ):
        return value

    if not isinstance(
        value,
        str,
    ):
        return GmailIntent.UNKNOWN

    value = value.strip().lower()

    try:
        return GmailIntent(value)

    except ValueError:
        return GmailIntent.UNKNOWN


# =============================================================
# Message reference normalization
# =============================================================


def normalize_message_reference(
    value: Any,
) -> MessageReference:
    """
    Normalize a Gmail message/thread reference.

    Supported forms:

        1
        5

        {"type": "position", "position": 3}
        {"type": "current"}
        {"type": "previous"}
        {"type": "latest"}
        {"type": "none"}

        "first email"
        "second email"
        "third email"
        "last email"
        "latest email"
        "previous email"
        "current email"
        "that email"
        "this email"
        "same email"
        "5"

    This function ONLY normalizes the semantic reference.

    It never creates or resolves a Gmail message ID/thread ID.
    """

    if value is None:
        return MessageReference()

    # ---------------------------------------------------------
    # Already normalized
    # ---------------------------------------------------------

    if isinstance(
        value,
        MessageReference,
    ):
        return value

    # ---------------------------------------------------------
    # Integer position
    # ---------------------------------------------------------

    if isinstance(
        value,
        int,
    ):
        if value > 0:
            return MessageReference(
                type=MessageReferenceType.POSITION,
                position=value,
                raw=str(value),
            )

        return MessageReference()

    # ---------------------------------------------------------
    # Natural-language reference
    # ---------------------------------------------------------

    if isinstance(
        value,
        str,
    ):
        text = value.strip().lower()

        if not text:
            return MessageReference()

        # -----------------------------------------------------
        # Normalize common reference wording
        # -----------------------------------------------------

        words = text.split()

        removable_words = {
            "the",
            "email",
            "emails",
            "mail",
            "message",
            "messages",
        }

        meaningful_words = [
            word
            for word in words
            if word not in removable_words
        ]

        reference_text = " ".join(
            meaningful_words
        ).strip()

        # -----------------------------------------------------
        # Numeric position
        # -----------------------------------------------------

        if reference_text.isdigit():
            position = int(
                reference_text
            )

            if position > 0:
                return MessageReference(
                    type=MessageReferenceType.POSITION,
                    position=position,
                    raw=text,
                )

            return MessageReference()

        # -----------------------------------------------------
        # Ordinal positions
        # -----------------------------------------------------

        ordinal_positions = {
            "first": 1,
            "1st": 1,
            "second": 2,
            "2nd": 2,
            "third": 3,
            "3rd": 3,
            "fourth": 4,
            "4th": 4,
            "fifth": 5,
            "5th": 5,
            "sixth": 6,
            "6th": 6,
            "seventh": 7,
            "7th": 7,
            "eighth": 8,
            "8th": 8,
            "ninth": 9,
            "9th": 9,
            "tenth": 10,
            "10th": 10,
        }

        if reference_text in ordinal_positions:
            position = ordinal_positions[
                reference_text
            ]

            return MessageReference(
                type=MessageReferenceType.POSITION,
                position=position,
                raw=text,
            )

        # -----------------------------------------------------
        # Contextual references
        # -----------------------------------------------------

        contextual_references = {
            "current": MessageReferenceType.CURRENT,
            "that": MessageReferenceType.CURRENT,
            "this": MessageReferenceType.CURRENT,
            "same": MessageReferenceType.CURRENT,

            "previous": MessageReferenceType.PREVIOUS,
            "last": MessageReferenceType.PREVIOUS,

            "latest": MessageReferenceType.LATEST,
            "newest": MessageReferenceType.LATEST,
        }

        if reference_text in contextual_references:
            reference_type = contextual_references[
                reference_text
            ]

            return MessageReference(
                type=reference_type,
                raw=text,
            )

        # -----------------------------------------------------
        # Unknown natural-language reference
        # -----------------------------------------------------

        return MessageReference()

    # ---------------------------------------------------------
    # Structured reference
    # ---------------------------------------------------------

    if not isinstance(
        value,
        dict,
    ):
        return MessageReference()

    reference_type = value.get(
        "type"
    )

    if not isinstance(
        reference_type,
        str,
    ):
        return MessageReference()

    # ---------------------------------------------------------
    # Validate reference type
    # ---------------------------------------------------------

    try:
        reference_type = MessageReferenceType(
            reference_type.strip().lower()
        )

    except ValueError:
        return MessageReference()

    # ---------------------------------------------------------
    # Position reference
    # ---------------------------------------------------------

    if (
        reference_type
        == MessageReferenceType.POSITION
    ):
        position = value.get(
            "position"
        )

        try:
            position = int(
                position
            )

        except (
            TypeError,
            ValueError,
        ):
            return MessageReference()

        if position <= 0:
            return MessageReference()

        raw = value.get(
            "raw"
        )

        return MessageReference(
            type=reference_type,
            position=position,
            raw=(
                str(raw).strip()
                if raw is not None
                else str(position)
            ),
        )

    # ---------------------------------------------------------
    # Non-position references
    # ---------------------------------------------------------

    raw = value.get(
        "raw"
    )

    return MessageReference(
        type=reference_type,
        raw=(
            str(raw).strip()
            if raw is not None
            else None
        ),
    )


# =============================================================
# Primitive normalization
# =============================================================


def _clean(
    value: Any,
) -> str | None:
    """
    Convert a value into a cleaned string.

    Empty values become None.
    """

    if value is None:
        return None

    value = str(
        value
    ).strip()

    return value or None


def _positive_int(
    value: Any,
) -> int | None:
    """
    Convert a value into a positive integer.

    Invalid or non-positive values become None.
    """

    if value is None:
        return None

    try:
        value = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    return (
        value
        if value > 0
        else None
    )


def _confidence(
    value: Any,
) -> float:
    """
    Normalize confidence to the range 0.0 - 1.0.
    """

    try:
        value = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        value = 0.0

    return max(
        0.0,
        min(
            1.0,
            value,
        ),
    )


# =============================================================
# Bedrock reference extraction
# =============================================================


def _extract_message_reference(
    data: dict[str, Any],
) -> Any:
    """
    Extract the message reference from Bedrock output.

    Supported forms:

        {
            "reference": {
                "type": "position",
                "position": 1
            }
        }

        {
            "reference": "first email"
        }

        {
            "reference": "position",
            "position": 1
        }

    The last form is converted into the canonical structure.
    """

    reference = data.get(
        "reference"
    )

    # ---------------------------------------------------------
    # Backward-compatible field
    # ---------------------------------------------------------

    if reference is None:
        reference = data.get(
            "message_reference"
        )

    # ---------------------------------------------------------
    # No reference
    # ---------------------------------------------------------

    if reference is None:
        return None

    # ---------------------------------------------------------
    # Separate reference type + position
    # ---------------------------------------------------------

    if isinstance(
        reference,
        str,
    ):
        reference_type = reference.strip().lower()

        if reference_type == "position":
            position = _positive_int(
                data.get("position")
            )

            if position is not None:
                return {
                    "type": "position",
                    "position": position,
                }

        if reference_type in {
            "current",
            "previous",
            "latest",
            "none",
        }:
            return {
                "type": reference_type,
            }

    return reference


# =============================================================
# Bedrock JSON -> application request
# =============================================================


def parse_bedrock_intent(
    data: dict[str, Any],
    raw_text: str | None = None,
) -> GmailIntentRequest:
    """
    Validate and normalize Bedrock's structured JSON.

    The application layer remains responsible for resolving
    semantic references against actual Gmail data.

    No Gmail account, message ID, thread ID or other
    user-specific identifier is generated here.
    """

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Bedrock intent must be a JSON object."
        )

    # ---------------------------------------------------------
    # Intent
    # ---------------------------------------------------------

    intent = normalize_intent(
        data.get("intent")
    )

    # ---------------------------------------------------------
    # Message reference
    # ---------------------------------------------------------

    message_reference_data = (
        _extract_message_reference(
            data
        )
    )

    message_reference = (
        normalize_message_reference(
            message_reference_data
        )
    )

    # ---------------------------------------------------------
    # Thread reference
    # ---------------------------------------------------------

    thread_reference_data = data.get(
        "thread_reference"
    )

    # ---------------------------------------------------------
    # Support:
    #
    # {
    #     "thread_reference": "position",
    #     "thread_position": 1
    # }
    # ---------------------------------------------------------

    if (
        isinstance(
            thread_reference_data,
            str,
        )
        and thread_reference_data.strip().lower()
        == "position"
    ):
        thread_position = _positive_int(
            data.get("thread_position")
        )

        if thread_position is not None:
            thread_reference_data = {
                "type": "position",
                "position": thread_position,
            }

    thread_reference = (
        normalize_message_reference(
            thread_reference_data
        )
    )

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    metadata = data.get(
        "metadata"
    )

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}

    # ---------------------------------------------------------
    # Build request
    # ---------------------------------------------------------

    return GmailIntentRequest(
        intent=intent,

        query=_clean(
            data.get("query")
        ),

        sender=_clean(
            data.get("sender")
        ),

        message_reference=message_reference,

        recipient=_clean(
            data.get("recipient")
        ),

        subject=_clean(
            data.get("subject")
        ),

        body=_clean(
            data.get("body")
        ),

        cc=_clean(
            data.get("cc")
        ),

        bcc=_clean(
            data.get("bcc")
        ),

        page=_positive_int(
            data.get("page")
        ),

        max_results=_positive_int(
            data.get("max_results")
        ),

        thread_reference=thread_reference,

        confidence=_confidence(
            data.get(
                "confidence",
                0.0,
            )
        ),

        raw_text=raw_text,

        metadata=metadata,
    )