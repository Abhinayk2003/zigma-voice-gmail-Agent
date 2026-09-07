from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agent.orchestrator import gmail_orchestrator


router = APIRouter(
    prefix="/agent",
    tags=["Gmail Agent"],
)


# =============================================================
# Request Model
# =============================================================

class AgentRequest(BaseModel):
    user_text: str = Field(
        ...,
        min_length=1,
        description="Natural-language Gmail request.",
    )


# =============================================================
# Authentication Helper
# =============================================================

def get_authenticated_account(
    request: Request,
) -> str:

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
# Process Gmail Agent Request
# =============================================================

@router.post("/process")
async def process_agent_request(
    payload: AgentRequest,
    request: Request,
) -> dict[str, Any]:

    account_email = get_authenticated_account(
        request
    )

    try:

        result = gmail_orchestrator.process(
            user_text=payload.user_text,
            account_email=account_email,
        )

        return result

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print("=" * 70)
        print("GMAIL AGENT REQUEST FAILED")
        print(
            "Exception type:",
            type(exc).__name__,
        )
        print(
            "Exception:",
            str(exc),
        )
        print("=" * 70)

        raise HTTPException(
            status_code=500,
            detail="Unable to process the Gmail agent request.",
        ) from exc
