
"""sync business database schema

Revision ID: aaaa922012c0
Revises: xxxxxxxxxxxx
Create Date: 2026-09-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aaaa922012c0"
down_revision: Union[str, Sequence[str], None] = "xxxxxxxxxxxx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Synchronize the existing business database schema
    with the SQLAlchemy models.

    The business tables already exist, so this migration
    only adds columns that are missing.
    """

    # ---------------------------------------------------------
    # ORDERS
    # ---------------------------------------------------------
    #
    # SQLAlchemy Order model contains delivered_at,
    # but the existing PostgreSQL orders table does not.
    #
    op.add_column(
        "orders",
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """
    Reverse the schema synchronization.
    """

    op.drop_column(
        "orders",
        "delivered_at",
    )

