from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.gmail.read import gmail_read_service
from app.gmail.send import gmail_send_service
from app.gmail.reply import gmail_reply_service
from app.gmail.service import gmail_service


router = APIRouter(
    prefix="/gmail",
    tags=["Gmail"],
)


# =============================================================
# Request Models
# =============================================================


class SendEmailRequest(BaseModel):
    """
    Request model for sending a Gmail message.

    All email fields are provided dynamically by the caller.
    """

    recipient: str = Field(
        ...,
        min_length=3,
        description="Recipient email address.",
    )

    subject: str = Field(
        ...,
        min_length=1,
        description="Email subject.",
    )

    body: str = Field(
        ...,
        min_length=1,
        description="Email body.",
    )

    cc: str | None = Field(
        default=None,
        description=(
            "Optional CC recipients. "
            "Multiple addresses can be comma-separated."
        ),
    )

    bcc: str | None = Field(
        default=None,
        description=(
            "Optional BCC recipients. "
            "Multiple addresses can be comma-separated."
        ),
    )


class ReplyEmailRequest(BaseModel):
    """
    Request model for replying to an existing Gmail message.

    Only the original Gmail message ID and reply body
    are required.

    Recipient, thread ID, subject and reply headers are
    determined dynamically from the original Gmail message.
    """

    message_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Original Gmail message ID to reply to."
        ),
    )

    body: str = Field(
        ...,
        min_length=1,
        description="Reply message body.",
    )


# =============================================================
# Authentication Helper
# =============================================================


def get_authenticated_account(
    request: Request,
) -> str:
    """
    Get the authenticated Gmail account from
    the current browser session.
    """

    account_email = request.session.get(
        "google_account_email"
    )

    if not account_email:

        raise HTTPException(
            status_code=401,
            detail=(
                "Gmail account is not authenticated. "
                "Please complete Google OAuth first."
            ),
        )

    return account_email


# =============================================================
# Gmail Authentication Status
# =============================================================


@router.get("/auth-status")
async def gmail_auth_status(
    request: Request,
):
    """
    Check whether a Gmail account is authenticated
    in the current session.
    """

    account_email = request.session.get(
        "google_account_email"
    )

    if not account_email:

        return {
            "success": True,
            "authenticated": False,
            "account_email": None,
        }

    return {
        "success": True,
        "authenticated": True,
        "account_email": account_email,
    }


# =============================================================
# Gmail Profile
# =============================================================


@router.get("/profile")
async def get_gmail_profile(
    request: Request,
):
    """
    Return the authenticated Gmail account profile.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        profile = gmail_service.get_profile(
            account_email
        )

        return {
            "success": True,
            "account_email": account_email,
            "gmail_profile": profile,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL PROFILE REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve Gmail profile."
            ),
        ) from exc


# =============================================================
# List Emails
# =============================================================


@router.get("/emails")
async def get_emails(
    request: Request,
    max_results: int | None = Query(
        default=None,
        ge=1,
        description=(
            "Maximum number of emails to return. "
            "Leave empty to use the configured/default Gmail limit."
        ),
    ),
    page_token: str | None = Query(
        default=None,
        description="Gmail pagination token.",
    ),
):
    """
    List Gmail messages.

    Pagination is supported through page_token.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.list_messages(
            account_email=account_email,
            query="",
            max_results=max_results,
            page_token=page_token,
        )

        return {
            "success": True,
            "account_email": account_email,
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL EMAIL LIST REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve Gmail emails."
            ),
        ) from exc


# =============================================================
# Unread Emails
# =============================================================


@router.get("/unread")
async def get_unread_emails(
    request: Request,
    max_results: int | None = Query(
        default=None,
        ge=1,
        description=(
            "Maximum number of unread emails to return."
        ),
    ),
    page_token: str | None = Query(
        default=None,
        description="Gmail pagination token.",
    ),
):
    """
    Retrieve unread Gmail messages.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.list_unread(
            account_email=account_email,
            max_results=max_results,
            page_token=page_token,
        )

        return {
            "success": True,
            "account_email": account_email,
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL UNREAD EMAIL REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve unread Gmail emails."
            ),
        ) from exc


# =============================================================
# Today's Emails
# =============================================================


@router.get("/today")
async def get_today_emails(
    request: Request,
    max_results: int | None = Query(
        default=None,
        ge=1,
        description=(
            "Maximum number of today's emails to return."
        ),
    ),
    page_token: str | None = Query(
        default=None,
        description="Gmail pagination token.",
    ),
):
    """
    Retrieve emails received today.

    The Gmail read service is responsible for the
    date filtering logic.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.list_today(
            account_email=account_email,
            max_results=max_results,
            page_token=page_token,
        )

        return {
            "success": True,
            "account_email": account_email,
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL TODAY EMAIL REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve today's Gmail emails."
            ),
        ) from exc


# =============================================================
# Search Emails
# =============================================================


@router.get("/search")
async def search_emails(
    request: Request,
    query: str = Query(
        ...,
        min_length=1,
        description=(
            "Gmail search query. "
            "Examples: is:unread, from:user@example.com, "
            "subject:invoice, newer_than:1d"
        ),
    ),
    max_results: int | None = Query(
        default=None,
        ge=1,
        description=(
            "Maximum number of matching emails to return."
        ),
    ),
    page_token: str | None = Query(
        default=None,
        description="Gmail pagination token.",
    ),
):
    """
    Search Gmail dynamically.

    Examples:

    /gmail/search?query=from:someone@example.com

    /gmail/search?query=subject:invoice

    /gmail/search?query=is:unread
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.search(
            account_email=account_email,
            query=query,
            max_results=max_results,
            page_token=page_token,
        )

        return {
            "success": True,
            "account_email": account_email,
            "query": query,
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL SEARCH REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to search Gmail."
            ),
        ) from exc


# =============================================================
# Send Email
# =============================================================


@router.post("/send")
async def send_email(
    request: Request,
    data: SendEmailRequest,
):
    """
    Send a new Gmail message.

    Recipient, subject, body, CC and BCC are supplied
    dynamically by the caller.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_send_service.send_email(
            account_email=account_email,
            recipient=data.recipient,
            subject=data.subject,
            body=data.body,
            cc=data.cc,
            bcc=data.bcc,
        )

        return {
            "success": True,
            "account_email": account_email,
            "message": (
                "Email sent successfully."
            ),
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL SEND REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL SEND REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to send Gmail message."
            ),
        ) from exc


# =============================================================
# Reply to Email
# =============================================================


@router.post("/reply")
async def reply_to_email(
    request: Request,
    data: ReplyEmailRequest,
):
    """
    Reply to an existing Gmail message.

    The original sender, subject, thread ID,
    Message-ID and References are determined
    dynamically from the original Gmail message.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = (
            gmail_reply_service.reply_to_message(
                account_email=account_email,
                message_id=data.message_id,
                body=data.body,
            )
        )

        return {
            "success": True,
            "account_email": account_email,
            "message": (
                "Gmail reply sent successfully."
            ),
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL REPLY REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL REPLY REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to reply to Gmail message."
            ),
        ) from exc


# =============================================================
# Get Single Email
# =============================================================


@router.get("/emails/{message_id}")
async def get_email(
    message_id: str,
    request: Request,
):
    """
    Retrieve one Gmail message by its dynamic message ID.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        message = (
            gmail_read_service.get_message(
                account_email=account_email,
                message_id=message_id,
            )
        )

        return {
            "success": True,
            "account_email": account_email,
            "message": message,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL MESSAGE REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL MESSAGE REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve Gmail message."
            ),
        ) from exc


# =============================================================
# Get Thread
# =============================================================


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    request: Request,
):
    """
    Retrieve a complete Gmail conversation/thread.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        thread = (
            gmail_read_service.get_thread(
                account_email=account_email,
                thread_id=thread_id,
            )
        )

        return {
            "success": True,
            "account_email": account_email,
            "thread": thread,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL THREAD REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL THREAD REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve Gmail thread."
            ),
        ) from exc
# =============================================================
# Mark Email as Read
# =============================================================

@router.post("/emails/{message_id}/read")
async def mark_email_as_read(
    message_id: str,
    request: Request,
):
    """
    Mark a Gmail message as read.

    The message ID is provided dynamically.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.mark_as_read(
            account_email=account_email,
            message_id=message_id,
        )

        return {
            "success": True,
            "account_email": account_email,
            "message": "Gmail message marked as read.",
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL MARK AS READ REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL MARK AS READ REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail="Unable to mark Gmail message as read.",
        ) from exc


# =============================================================
# Mark Email as Unread
# =============================================================

@router.post("/emails/{message_id}/unread")
async def mark_email_as_unread(
    message_id: str,
    request: Request,
):
    """
    Mark a Gmail message as unread.

    The message ID is provided dynamically.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.mark_as_unread(
            account_email=account_email,
            message_id=message_id,
        )

        return {
            "success": True,
            "account_email": account_email,
            "message": "Gmail message marked as unread.",
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL MARK AS UNREAD REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL MARK AS UNREAD REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail="Unable to mark Gmail message as unread.",
        ) from exc
# =============================================================
# Star Email
# =============================================================

@router.post("/emails/{message_id}/star")
async def star_email(
    message_id: str,
    request: Request,
):
    """
    Star a Gmail message.

    The message ID is provided dynamically.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.star_message(
            account_email=account_email,
            message_id=message_id,
        )

        return {
            "success": True,
            "account_email": account_email,
            "message": "Gmail message starred.",
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL STAR REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL STAR REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail="Unable to star Gmail message.",
        ) from exc


# =============================================================
# Unstar Email
# =============================================================

@router.post("/emails/{message_id}/unstar")
async def unstar_email(
    message_id: str,
    request: Request,
):
    """
    Remove the star from a Gmail message.

    The message ID is provided dynamically.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.unstar_message(
            account_email=account_email,
            message_id=message_id,
        )

        return {
            "success": True,
            "account_email": account_email,
            "message": "Gmail message unstarred.",
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL UNSTAR REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL UNSTAR REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail="Unable to unstar Gmail message.",
        ) from exc
# =============================================================
# Move Email to Trash
# =============================================================

@router.delete("/emails/{message_id}")
async def delete_email(
    message_id: str,
    request: Request,
):
    """
    Move a Gmail message to Trash.

    The message ID is provided dynamically.
    """

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_read_service.delete_message(
            account_email=account_email,
            message_id=message_id,
        )

        return {
            "success": True,
            "account_email": account_email,
            "message": "Gmail message moved to Trash.",
            **result,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        print("=" * 70)
        print("GMAIL DELETE REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL DELETE REQUEST FAILED")
        print("Exception type:", type(exc).__name__)
        print("Exception:", str(exc))
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail="Unable to move Gmail message to Trash.",
        ) from exc