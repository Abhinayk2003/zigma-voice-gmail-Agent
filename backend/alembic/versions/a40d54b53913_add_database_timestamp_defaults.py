"""add database timestamp defaults

Revision ID: a40d54b53913
Revises: aaaa922012c0
Create Date: 2026-09-09 16:05:00.110094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a40d54b53913'
down_revision: Union[str, Sequence[str], None] = 'aaaa922012c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
