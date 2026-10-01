"""add timestamp defaults

Revision ID: 50f15e4e0c9d
Revises: a40d54b53913
Create Date: 2026-09-09 16:07:01.476622

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "50f15e4e0c9d"
down_revision: Union[str, Sequence[str], None] = "a40d54b53913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add database-side timestamp defaults."""

    op.alter_column(
        "conversation_messages",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_nullable=False,
    )

    op.alter_column(
        "conversation_actions",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_nullable=False,
    )

    op.alter_column(
        "conversation_workflows",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_nullable=False,
    )

    op.alter_column(
        "conversation_workflows",
        "updated_at",
        existing_type=sa.DateTime(),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Remove database-side timestamp defaults."""

    op.alter_column(
        "conversation_messages",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "conversation_actions",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "conversation_workflows",
        "created_at",
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "conversation_workflows",
        "updated_at",
        existing_type=sa.DateTime(),
        server_default=None,
        existing_nullable=False,
    )
