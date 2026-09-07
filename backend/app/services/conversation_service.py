from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    Conversation,
    ConversationMessage,
    ConversationAction,
    ConversationWorkflow,
    User,
    GmailAccount,
)


class ConversationService:
    """
    Handles durable conversation/session-related application
    state.

    IMPORTANT:

    AgentCore Memory is the primary conversational memory
    system.

    PostgreSQL is used for:

        - Conversation/session reference
        - Gmail actions
        - Confirmation state
        - Persistent workflows
        - Optional legacy message history

    PostgreSQL should not be treated as the main LLM
    conversational-memory store.
    """

    # =========================================================
    # Get or Create Active Conversation
    # =========================================================

    @staticmethod
    def get_or_create_conversation(
        db: Session,
        user: User,
        gmail_account: GmailAccount | None = None,
    ) -> Conversation:

        query = (
            select(Conversation)
            .where(
                Conversation.user_id == user.id,
                Conversation.is_active.is_(True),
            )
            .order_by(
                Conversation.updated_at.desc(),
                Conversation.id.desc(),
            )
        )

        conversation = db.scalar(query)

        if conversation:

            # -------------------------------------------------
            # Keep the authenticated Gmail account association
            # current.
            # -------------------------------------------------

            if (
                gmail_account is not None
                and conversation.gmail_account_id
                != gmail_account.id
            ):
                conversation.gmail_account_id = (
                    gmail_account.id
                )

                conversation.updated_at = (
                    datetime.utcnow()
                )

                db.commit()
                db.refresh(conversation)

            return conversation

        conversation = Conversation(
            user_id=user.id,
            gmail_account_id=(
                gmail_account.id
                if gmail_account
                else None
            ),
            is_active=True,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return conversation

    # =========================================================
    # Start New Conversation
    # =========================================================

    @staticmethod
    def create_new_conversation(
        db: Session,
        user: User,
        gmail_account: GmailAccount | None = None,
        title: str | None = None,
    ) -> Conversation:
        """
        Explicitly create a new application conversation.

        This can be useful when the UI/user starts a new
        AgentCore Memory session.
        """

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
    # Close Conversation
    # =========================================================

    @staticmethod
    def close_conversation(
        db: Session,
        conversation: Conversation,
    ) -> Conversation:

        conversation.is_active = False
        conversation.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(conversation)

        return conversation

    # =========================================================
    # Save User Message
    # =========================================================

    @staticmethod
    def save_user_message(
        db: Session,
        conversation: Conversation,
        content: str,
        intent: str | None = None,
    ) -> ConversationMessage:
        """
        Optional compatibility/history storage.

        The actual conversational memory should be written
        to AgentCore Memory by the agent layer.
        """

        if content is None:
            raise ValueError(
                "User message content is required."
            )

        message = ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content=str(content),
            intent=intent,
        )

        db.add(message)

        conversation.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(message)

        return message

    # =========================================================
    # Save Assistant Message
    # =========================================================

    @staticmethod
    def save_assistant_message(
        db: Session,
        conversation: Conversation,
        content: str,
        intent: str | None = None,
    ) -> ConversationMessage:
        """
        Optional compatibility/history storage.

        AgentCore Memory remains the primary conversation
        memory source.
        """

        if content is None:
            raise ValueError(
                "Assistant message content is required."
            )

        message = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=str(content),
            intent=intent,
        )

        db.add(message)

        conversation.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(message)

        return message

    # =========================================================
    # Save Gmail Action
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

        if not action_type or not action_type.strip():
            raise ValueError(
                "Action type is required."
            )

        if not status or not status.strip():
            raise ValueError(
                "Action status is required."
            )

        normalized_status = status.strip().lower()

        action = ConversationAction(
            conversation_id=conversation.id,
            action_type=action_type.strip().lower(),
            status=normalized_status,
            gmail_message_id=gmail_message_id,
            gmail_thread_id=gmail_thread_id,
            sender=sender,
            recipient=recipient,
            subject=subject,
            details=details,
            completed_at=completed_at,
        )

        if (
            completed_at is None
            and normalized_status
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
    # GET PENDING CONFIRMATION
    # =========================================================

    @staticmethod
    def get_pending_action(
        db: Session,
        conversation: Conversation,
    ) -> dict | None:
        """
        Retrieve the latest Gmail action waiting for
        confirmation.

        This allows destructive confirmation to survive
        application restarts.
        """

        query = (
            select(ConversationAction)
            .where(
                ConversationAction.conversation_id
                == conversation.id,
                ConversationAction.status
                == "pending_confirmation",
            )
            .order_by(
                ConversationAction.created_at.desc(),
                ConversationAction.id.desc(),
            )
        )

        action = db.scalar(query)

        if not action:
            return None

        result = {
            "action": action.action_type,
            "action_id": action.id,
            "status": action.status,

            "gmail_message_id": (
                action.gmail_message_id
            ),

            "gmail_thread_id": (
                action.gmail_thread_id
            ),

            "sender": action.sender,
            "recipient": action.recipient,
            "subject": action.subject,

            "details": action.details or {},
        }

        return result

    # =========================================================
    # RESOLVE PENDING CONFIRMATION
    # =========================================================

    @staticmethod
    def resolve_pending_actions(
        db: Session,
        conversation: Conversation,
        status: str = "completed",
    ) -> None:
        """
        Resolve all pending confirmation actions belonging
        to this conversation.
        """

        if not status or not status.strip():
            raise ValueError(
                "Resolution status is required."
            )

        normalized_status = status.strip().lower()

        query = (
            select(ConversationAction)
            .where(
                ConversationAction.conversation_id
                == conversation.id,
                ConversationAction.status
                == "pending_confirmation",
            )
        )

        actions = db.scalars(query).all()

        now = datetime.utcnow()

        for action in actions:
            action.status = normalized_status
            action.completed_at = now

        conversation.updated_at = now

        db.commit()

    # =========================================================
    # Resolve Specific Pending Action
    # =========================================================

    @staticmethod
    def resolve_action(
        db: Session,
        action: ConversationAction,
        status: str,
        details: dict | None = None,
    ) -> ConversationAction:
        """
        Resolve one specific action.

        Useful when multiple historical actions exist and
        only one confirmation needs to be completed.
        """

        if not status or not status.strip():
            raise ValueError(
                "Action status is required."
            )

        action.status = status.strip().lower()

        if details is not None:
            action.details = details

        action.completed_at = datetime.utcnow()

        db.commit()
        db.refresh(action)

        return action

    # =========================================================
    # GET CONVERSATION HISTORY
    # =========================================================

    @staticmethod
    def get_messages(
        db: Session,
        conversation: Conversation,
        limit: int = 20,
    ) -> list[ConversationMessage]:
        """
        Optional legacy/application history.

        Do not use this as the primary conversational-memory
        mechanism for the agent.
        """

        if limit <= 0:
            return []

        query = (
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id
                == conversation.id
            )
            .order_by(
                ConversationMessage.created_at.desc(),
                ConversationMessage.id.desc(),
            )
            .limit(limit)
        )

        messages = list(
            db.scalars(query)
        )

        messages.reverse()

        return messages

    # =========================================================
    # GET RECENT ACTIONS
    # =========================================================

    @staticmethod
    def get_actions(
        db: Session,
        conversation: Conversation,
        limit: int = 20,
    ) -> list[ConversationAction]:

        if limit <= 0:
            return []

        query = (
            select(ConversationAction)
            .where(
                ConversationAction.conversation_id
                == conversation.id
            )
            .order_by(
                ConversationAction.created_at.desc(),
                ConversationAction.id.desc(),
            )
            .limit(limit)
        )

        actions = list(
            db.scalars(query)
        )

        actions.reverse()

        return actions

    # =========================================================
    # CREATE WORKFLOW
    # =========================================================

    @staticmethod
    def create_workflow(
        db: Session,
        conversation: Conversation,
        workflow_type: str,
        status: str = "WAITING_FOR_INPUT",
        required_field: str | None = None,
        collected_data: dict | None = None,
    ) -> ConversationWorkflow:
        """
        Create a persistent multi-step workflow.
        """

        if not workflow_type or not workflow_type.strip():
            raise ValueError(
                "Workflow type is required."
            )

        if not status or not status.strip():
            raise ValueError(
                "Workflow status is required."
            )

        if collected_data is not None:
            if not isinstance(
                collected_data,
                dict,
            ):
                raise ValueError(
                    "Collected workflow data must be a dictionary."
                )

        workflow = ConversationWorkflow(
            conversation_id=conversation.id,
            workflow_type=workflow_type.strip(),
            status=status.strip().upper(),
            required_field=(
                required_field.strip()
                if required_field
                and required_field.strip()
                else None
            ),
            collected_data=(
                collected_data
                if collected_data is not None
                else {}
            ),
        )

        db.add(workflow)

        conversation.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(workflow)

        return workflow

    # =========================================================
    # GET ACTIVE WORKFLOW
    # =========================================================

    @staticmethod
    def get_active_workflow(
        db: Session,
        conversation: Conversation,
    ) -> ConversationWorkflow | None:
        """
        Return the most recent unfinished workflow.

        Active states:

            WAITING_FOR_INPUT
            READY
            EXECUTING
        """

        query = (
            select(ConversationWorkflow)
            .where(
                ConversationWorkflow.conversation_id
                == conversation.id,
                ConversationWorkflow.status.in_(
                    [
                        "WAITING_FOR_INPUT",
                        "READY",
                        "EXECUTING",
                    ]
                ),
            )
            .order_by(
                ConversationWorkflow.updated_at.desc(),
                ConversationWorkflow.id.desc(),
            )
        )

        return db.scalar(query)

    # =========================================================
    # UPDATE WORKFLOW
    # =========================================================

    @staticmethod
    def update_workflow(
        db: Session,
        workflow: ConversationWorkflow,
        *,
        status: str | None = None,
        required_field: str | None = None,
        collected_data: dict | None = None,
    ) -> ConversationWorkflow:
        """
        Update one or more workflow fields.

        Each field is updated independently.

        This fixes the previous issue where required_field
        was only updated when status was supplied.
        """

        # -----------------------------------------------------
        # Status
        # -----------------------------------------------------

        if status is not None:

            if not status.strip():
                raise ValueError(
                    "Workflow status cannot be empty."
                )

            workflow.status = status.strip().upper()

        # -----------------------------------------------------
        # Required field
        # -----------------------------------------------------

        if required_field is not None:

            workflow.required_field = (
                required_field.strip()
                if required_field.strip()
                else None
            )

        # -----------------------------------------------------
        # Collected data
        # -----------------------------------------------------

        if collected_data is not None:

            if not isinstance(
                collected_data,
                dict,
            ):
                raise ValueError(
                    "Collected workflow data must be a dictionary."
                )

            workflow.collected_data = collected_data

        workflow.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(workflow)

        return workflow

    # =========================================================
    # COMPLETE WORKFLOW
    # =========================================================

    @staticmethod
    def complete_workflow(
        db: Session,
        workflow: ConversationWorkflow,
    ) -> ConversationWorkflow:
        """
        Mark workflow as completed.

        Historical collected data remains stored.
        """

        workflow.status = "COMPLETED"
        workflow.required_field = None
        workflow.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(workflow)

        return workflow

    # =========================================================
    # CANCEL WORKFLOW
    # =========================================================

    @staticmethod
    def cancel_workflow(
        db: Session,
        workflow: ConversationWorkflow,
    ) -> ConversationWorkflow:
        """
        Cancel an unfinished workflow.

        Collected data remains preserved.
        """

        workflow.status = "CANCELLED"
        workflow.required_field = None
        workflow.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(workflow)

        return workflow