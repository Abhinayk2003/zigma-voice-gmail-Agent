from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    User,
    GmailAccount,
    Conversation,
    ConversationMessage,
    ConversationAction,
)


class DatabaseService:
    """
    Handles persistent application data stored in PostgreSQL.

    PostgreSQL is responsible for:

        - Users
        - Gmail accounts
        - Conversation/session references
        - Gmail actions
        - Audit information

    AgentCore Memory is responsible for the actual
    conversational memory.
    """

    # =========================================================
    # User
    # =========================================================

    @staticmethod
    def get_or_create_user(
        db: Session,
        email: str,
        display_name: str | None = None,
    ) -> User:

        if not email or not email.strip():
            raise ValueError(
                "User email is required."
            )

        email = email.strip().lower()

        user = db.scalar(
            select(User).where(
                User.email == email
            )
        )

        if user:

            if display_name is not None:
                user.display_name = display_name

            if not user.is_active:
                user.is_active = True

            db.commit()
            db.refresh(user)

            return user

        user = User(
            email=email,
            display_name=display_name,
            is_active=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    # =========================================================
    # Gmail Account
    # =========================================================

    @staticmethod
    def get_or_create_gmail_account(
        db: Session,
        user: User,
        email: str,
        provider: str = "google",
    ) -> GmailAccount:

        if not email or not email.strip():
            raise ValueError(
                "Gmail account email is required."
            )

        email = email.strip().lower()

        provider = (
            provider.strip().lower()
            if provider
            else "google"
        )

        account = db.scalar(
            select(GmailAccount).where(
                GmailAccount.user_id == user.id,
                GmailAccount.email == email,
            )
        )

        if account:

            account.provider = provider
            account.is_active = True

            db.commit()
            db.refresh(account)

            return account

        account = GmailAccount(
            user_id=user.id,
            email=email,
            provider=provider,
            is_active=True,
        )

        db.add(account)
        db.commit()
        db.refresh(account)

        return account

    # =========================================================
    # Conversation
    # =========================================================

    @staticmethod
    def create_conversation(
        db: Session,
        user: User,
        gmail_account: GmailAccount | None = None,
        title: str | None = None,
    ) -> Conversation:

        conversation = Conversation(
            user_id=user.id,
            gmail_account_id=(
                gmail_account.id
                if gmail_account
                else None
            ),
            title=title,
            is_active=True,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return conversation

    # =========================================================
    # Save Message
    # =========================================================

    @staticmethod
    def save_message(
        db: Session,
        conversation: Conversation,
        role: str,
        content: str,
        intent: str | None = None,
    ) -> ConversationMessage:
        """
        Compatibility method for optional application-level
        message history.

        AgentCore Memory should remain the primary source
        of conversational memory.
        """

        if not role or not role.strip():
            raise ValueError(
                "Message role is required."
            )

        if content is None:
            raise ValueError(
                "Message content is required."
            )

        message = ConversationMessage(
            conversation_id=conversation.id,
            role=role.strip().lower(),
            content=str(content),
            intent=intent,
        )

        db.add(message)

        conversation.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(message)

        return message

    # =========================================================
    # Save Action
    # =========================================================

    @staticmethod
    def save_action(
        db: Session,
        conversation: Conversation,
        action_type: str,
        status: str = "success",
        details: dict | None = None,
        *,
        gmail_message_id: str | None = None,
        gmail_thread_id: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        subject: str | None = None,
        completed_at: datetime | None = None,
    ) -> ConversationAction:
        """
        Save a structured Gmail action.

        Examples:

            send
            reply
            delete
            archive
            star
            search
            read

        Gmail identifiers and email metadata are stored in
        dedicated columns instead of hiding everything inside
        a text field.
        """

        if not action_type or not action_type.strip():
            raise ValueError(
                "Action type is required."
            )

        if not status or not status.strip():
            raise ValueError(
                "Action status is required."
            )

        action = ConversationAction(
            conversation_id=conversation.id,
            action_type=action_type.strip().lower(),
            status=status.strip().lower(),
            gmail_message_id=gmail_message_id,
            gmail_thread_id=gmail_thread_id,
            sender=sender,
            recipient=recipient,
            subject=subject,
            details=details,
            completed_at=completed_at,
        )

        # -----------------------------------------------------
        # Automatically mark completed successful/failed
        # actions with a completion timestamp.
        # Pending confirmation remains incomplete.
        # -----------------------------------------------------

        if (
            completed_at is None
            and status.strip().lower()
            not in {
                "pending_confirmation",
                "pending",
            }
        ):
            action.completed_at = datetime.utcnow()

        db.add(action)

        conversation.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(action)

        return action

    # =========================================================
    # Update Action Status
    # =========================================================

    @staticmethod
    def update_action_status(
        db: Session,
        action: ConversationAction,
        status: str,
        *,
        details: dict | None = None,
    ) -> ConversationAction:
        """
        Update the status of an existing Gmail action.
        """

        if not status or not status.strip():
            raise ValueError(
                "Action status is required."
            )

        action.status = status.strip().lower()

        if details is not None:
            action.details = details

        if action.status not in {
            "pending_confirmation",
            "pending",
        }:
            action.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(action)

        return action