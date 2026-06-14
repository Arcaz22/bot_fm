"""add phone number to telegram user

Revision ID: 9b2d4f6a8c11
Revises: 6e1bcafe433e
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b2d4f6a8c11"
down_revision: Union[str, Sequence[str], None] = "6e1bcafe433e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sys_telegram_user", sa.Column("phone_number", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_sys_telegram_user_phone_number"), "sys_telegram_user", ["phone_number"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_telegram_user_phone_number"), table_name="sys_telegram_user")
    op.drop_column("sys_telegram_user", "phone_number")
