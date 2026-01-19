"""menambahkan transfer di category

Revision ID: c69b561689a0
Revises: 2ed1bfb43f61
Create Date: 2026-01-19 14:24:15.379992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c69b561689a0'
down_revision: Union[str, Sequence[str], None] = '2ed1bfb43f61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hapus constraint lama
    op.drop_constraint('ck_category_type', 'mst_category', type_='check')
    # Buat baru dengan 'transfer'
    op.create_check_constraint(
        'ck_category_type',
        'mst_category',
        "type IN ('income', 'expense', 'transfer')"
    )

def downgrade() -> None:
    op.drop_constraint('ck_category_type', 'mst_category', type_='check')
    op.create_check_constraint(
        'ck_category_type',
        'mst_category',
        "type IN ('income', 'expense')"
    )
