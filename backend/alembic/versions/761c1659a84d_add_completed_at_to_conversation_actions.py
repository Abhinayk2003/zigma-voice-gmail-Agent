"""add completed at to conversation actions

Revision ID: 761c1659a84d
Revises: b912f17409c2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "761c1659a84d"
down_revision: Union[str, Sequence[str], None] = "b912f17409c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add completed_at column to conversation_actions."""

    op.add_column(
        "conversation_actions",
        sa.Column(
            "completed_at",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove completed_at column from conversation_actions."""

    op.drop_column(
        "conversation_actions",
        "completed_at",
    )
