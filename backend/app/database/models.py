from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


# =========================================================
# Users
# =========================================================

class User(Base):
    """
    Application user.

    Stores identity information only.

    OAuth credentials/tokens must NOT be stored here.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        nullable=False,
        index=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # -----------------------------------------------------
    # Relationships
    # -----------------------------------------------------

    gmail_accounts: Mapped[list["GmailAccount"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


# =========================================================
# Gmail Accounts
# =========================================================

class GmailAccount(Base):
    """
    Gmail account connected to an application user.

    Only account metadata is stored here.

    Gmail OAuth tokens/credentials are intentionally NOT
    stored in PostgreSQL.
    """

    __tablename__ = "gmail_accounts"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "email",
            name="uq_gmail_account_user_email",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="google",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # -----------------------------------------------------
    # Relationships
    # -----------------------------------------------------

    user: Mapped["User"] = relationship(
        back_populates="gmail_accounts",
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="gmail_account",
    )


# =========================================================
# Conversations
# =========================================================

class Conversation(Base):
    """
    Application-level conversation/session.

    IMPORTANT:

    The actual conversational memory should be handled by
    AgentCore Memory.

    PostgreSQL keeps the durable application-level reference
    and associates actions/workflows with this conversation.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    gmail_account_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "gmail_accounts.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # -----------------------------------------------------
    # Relationships
    # -----------------------------------------------------

    user: Mapped["User"] = relationship(
        back_populates="conversations",
    )

    gmail_account: Mapped["GmailAccount | None"] = relationship(
        back_populates="conversations",
    )

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    actions: Mapped[list["ConversationAction"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    workflows: Mapped[list["ConversationWorkflow"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


# =========================================================
# Conversation Messages
# =========================================================

class ConversationMessage(Base):
    """
    Legacy/persistent message history.

    AgentCore Memory is the primary conversational memory
    system for the Zigma agent.

    This table is retained for compatibility, auditing,
    migration, or optional application-level history.

    The agent should NOT depend on this table as its primary
    conversation-memory mechanism.
    """

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    intent: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    # -----------------------------------------------------
    # Relationships
    # -----------------------------------------------------

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
    )


# =========================================================
# Conversation Actions
# =========================================================

class ConversationAction(Base):
    """
    Durable Gmail action/audit record.

    This is one of the most important PostgreSQL tables
    for the Zigma Gmail Agent.

    Examples:

        send
        reply
        delete
        archive
        star
        unstar
        mark_read
        mark_unread
        search
        read

    The table stores structured Gmail identifiers and
    action metadata.

    It also supports persistent destructive-action
    confirmation.
    """

    __tablename__ = "conversation_actions"

    __table_args__ = (
        Index(
            "ix_action_conversation_created",
            "conversation_id",
            "created_at",
        ),
        Index(
            "ix_action_gmail_message",
            "gmail_message_id",
        ),
        Index(
            "ix_action_gmail_thread",
            "gmail_thread_id",
        ),
        Index(
            "ix_action_status",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # -----------------------------------------------------
    # Action
    # -----------------------------------------------------

    action_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="success",
        index=True,
    )

    # -----------------------------------------------------
    # Gmail identifiers
    # -----------------------------------------------------

    gmail_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    gmail_thread_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # -----------------------------------------------------
    # Email information
    # -----------------------------------------------------

    sender: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )

    recipient: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )

    subject: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    # -----------------------------------------------------
    # Flexible action details
    # -----------------------------------------------------

    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # -----------------------------------------------------
    # Timestamps
    # -----------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # -----------------------------------------------------
    # Relationships
    # -----------------------------------------------------

    conversation: Mapped["Conversation"] = relationship(
        back_populates="actions",
    )


# =========================================================
# Conversation Workflows
# =========================================================

class ConversationWorkflow(Base):
    """
    Persistent multi-step workflow state.

    This is NOT conversational memory.

    It stores business/process state that must survive
    application restarts.

    Examples:

        invoice processing
        ticket handling
        booking workflow
        customer lookup
        order processing
        multi-step Gmail operation
    """

    __tablename__ = "conversation_workflows"

    __table_args__ = (
        Index(
            "ix_workflow_conversation_status",
            "conversation_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # -----------------------------------------------------
    # Workflow information
    # -----------------------------------------------------

    workflow_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="WAITING_FOR_INPUT",
        index=True,
    )

    required_field: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # -----------------------------------------------------
    # Dynamic workflow information
    # -----------------------------------------------------

    collected_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # -----------------------------------------------------
    # Timestamps
    # -----------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # -----------------------------------------------------
    # Relationships
    # -----------------------------------------------------

    conversation: Mapped["Conversation"] = relationship(
        back_populates="workflows",
    )