"""v001_initial_schema

Revision ID: ecb932800c60
Revises: 5297d9118703
Create Date: 2026-03-20 22:21:14.750822

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ecb932800c60'
down_revision: Union[str, Sequence[str], None] = '5297d9118703'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
