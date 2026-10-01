"""add metadata json to order events

Revision ID: 0dad12ae7d25
Revises: 50f15e4e0c9d
Create Date: 2026-09-11 17:05:35.735950

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0dad12ae7d25"
down_revision: Union[str, Sequence[str], None] = "50f15e4e0c9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add metadata_json column to order_events."""

    op.add_column(
        "order_events",
        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove metadata_json column from order_events."""

    op.drop_column(
        "order_events",
        "metadata_json",
    )
