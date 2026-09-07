"""add gmail metadata to conversation actions

Revision ID: b912f17409c2
Revises: 1de9e462f420
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b912f17409c2"
down_revision: Union[str, Sequence[str], None] = "1de9e462f420"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_actions",
        sa.Column(
            "gmail_message_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "conversation_actions",
        sa.Column(
            "gmail_thread_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "conversation_actions",
        sa.Column(
            "sender",
            sa.String(length=320),
            nullable=True,
        ),
    )

    op.add_column(
        "conversation_actions",
        sa.Column(
            "recipient",
            sa.String(length=320),
            nullable=True,
        ),
    )

    op.add_column(
        "conversation_actions",
        sa.Column(
            "subject",
            sa.String(length=1000),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_action_gmail_message",
        "conversation_actions",
        ["gmail_message_id"],
        unique=False,
    )

    op.create_index(
        "ix_action_gmail_thread",
        "conversation_actions",
        ["gmail_thread_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_action_gmail_thread",
        table_name="conversation_actions",
    )

    op.drop_index(
        "ix_action_gmail_message",
        table_name="conversation_actions",
    )

    op.drop_column(
        "conversation_actions",
        "subject",
    )

    op.drop_column(
        "conversation_actions",
        "recipient",
    )

    op.drop_column(
        "conversation_actions",
        "sender",
    )

    op.drop_column(
        "conversation_actions",
        "gmail_thread_id",
    )

    op.drop_column(
        "conversation_actions",
        "gmail_message_id",
    )
