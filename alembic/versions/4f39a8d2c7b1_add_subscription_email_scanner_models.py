"""add subscription email scanner models

Revision ID: 4f39a8d2c7b1
Revises: e13d2a67902a
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4f39a8d2c7b1"
down_revision: Union[str, Sequence[str], None] = "e13d2a67902a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_email_account",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("sync_cursor", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider IN ('google','microsoft')", name="ck_sub_email_provider"),
        sa.CheckConstraint(
            "status IN ('connected','syncing','needs_reauth','disconnected','error')",
            name="ck_sub_email_status",
        ),
        sa.ForeignKeyConstraint(["owner_telegram_user_id"], ["sys_telegram_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_telegram_user_id",
            "provider",
            "email_address",
            name="uq_subscription_email_account_owner_provider_email",
        ),
    )
    op.create_index(
        "idx_sub_email_owner_status",
        "subscription_email_account",
        ["owner_telegram_user_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_email_account_email_address"),
        "subscription_email_account",
        ["email_address"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_email_account_owner_telegram_user_id"),
        "subscription_email_account",
        ["owner_telegram_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_email_account_status"),
        "subscription_email_account",
        ["status"],
        unique=False,
    )

    op.create_table(
        "subscription_detection",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("email_account_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=False),
        sa.Column("merchant_name", sa.String(length=150), nullable=True),
        sa.Column("plan_name", sa.String(length=150), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("billing_period", sa.String(length=20), nullable=False),
        sa.Column("billing_date", sa.Date(), nullable=True),
        sa.Column("next_billing_date", sa.Date(), nullable=True),
        sa.Column("payment_method", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("raw_subject", sa.String(length=500), nullable=True),
        sa.Column("raw_sender", sa.String(length=255), nullable=True),
        sa.Column("llm_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "billing_period IN ('weekly','monthly','yearly','one_time','unknown')",
            name="ck_sub_detection_billing_period",
        ),
        sa.CheckConstraint(
            "status IN ('needs_review','confirmed','ignored','merged')",
            name="ck_sub_detection_status",
        ),
        sa.ForeignKeyConstraint(["email_account_id"], ["subscription_email_account.id"]),
        sa.ForeignKeyConstraint(["owner_telegram_user_id"], ["sys_telegram_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "email_account_id",
            "source_message_id",
            name="uq_subscription_detection_email_message",
        ),
    )
    op.create_index(
        "idx_sub_detection_email_status",
        "subscription_detection",
        ["email_account_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_sub_detection_owner_status",
        "subscription_detection",
        ["owner_telegram_user_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_detection_email_account_id"),
        "subscription_detection",
        ["email_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_detection_owner_telegram_user_id"),
        "subscription_detection",
        ["owner_telegram_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_detection_status"),
        "subscription_detection",
        ["status"],
        unique=False,
    )

    op.create_table(
        "subscription",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("email_account_id", sa.BigInteger(), nullable=True),
        sa.Column("merchant_name", sa.String(length=150), nullable=False),
        sa.Column("plan_name", sa.String(length=150), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("billing_period", sa.String(length=20), nullable=False),
        sa.Column("next_billing_date", sa.Date(), nullable=True),
        sa.Column("wallet_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "billing_period IN ('weekly','monthly','yearly','one_time','unknown')",
            name="ck_sub_subscription_billing_period",
        ),
        sa.CheckConstraint("source IN ('email_scan','manual')", name="ck_sub_subscription_source"),
        sa.CheckConstraint(
            "status IN ('active','cancelled','paused','unknown')",
            name="ck_sub_subscription_status",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["mst_category.id"]),
        sa.ForeignKeyConstraint(["email_account_id"], ["subscription_email_account.id"]),
        sa.ForeignKeyConstraint(["owner_telegram_user_id"], ["sys_telegram_user.id"]),
        sa.ForeignKeyConstraint(["wallet_id"], ["mst_wallet.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sub_subscription_owner_next_billing",
        "subscription",
        ["owner_telegram_user_id", "next_billing_date"],
        unique=False,
    )
    op.create_index(
        "idx_sub_subscription_owner_status",
        "subscription",
        ["owner_telegram_user_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_subscription_email_account_id"), "subscription", ["email_account_id"], unique=False)
    op.create_index(
        op.f("ix_subscription_owner_telegram_user_id"),
        "subscription",
        ["owner_telegram_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_subscription_status"), "subscription", ["status"], unique=False)

    op.create_table(
        "subscription_payment",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("paid_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("billing_period_start", sa.Date(), nullable=True),
        sa.Column("billing_period_end", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('email_scan','manual','telegram')", name="ck_sub_payment_source"),
        sa.ForeignKeyConstraint(["owner_telegram_user_id"], ["sys_telegram_user.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscription.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["trs_transaction.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sub_payment_owner_paid_at",
        "subscription_payment",
        ["owner_telegram_user_id", "paid_at"],
        unique=False,
    )
    op.create_index(
        "idx_sub_payment_subscription_paid_at",
        "subscription_payment",
        ["subscription_id", "paid_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_payment_owner_telegram_user_id"),
        "subscription_payment",
        ["owner_telegram_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_payment_subscription_id"),
        "subscription_payment",
        ["subscription_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_payment_transaction_id"),
        "subscription_payment",
        ["transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_subscription_payment_transaction_id"), table_name="subscription_payment")
    op.drop_index(op.f("ix_subscription_payment_subscription_id"), table_name="subscription_payment")
    op.drop_index(op.f("ix_subscription_payment_owner_telegram_user_id"), table_name="subscription_payment")
    op.drop_index("idx_sub_payment_subscription_paid_at", table_name="subscription_payment")
    op.drop_index("idx_sub_payment_owner_paid_at", table_name="subscription_payment")
    op.drop_table("subscription_payment")

    op.drop_index(op.f("ix_subscription_status"), table_name="subscription")
    op.drop_index(op.f("ix_subscription_owner_telegram_user_id"), table_name="subscription")
    op.drop_index(op.f("ix_subscription_email_account_id"), table_name="subscription")
    op.drop_index("idx_sub_subscription_owner_status", table_name="subscription")
    op.drop_index("idx_sub_subscription_owner_next_billing", table_name="subscription")
    op.drop_table("subscription")

    op.drop_index(op.f("ix_subscription_detection_status"), table_name="subscription_detection")
    op.drop_index(op.f("ix_subscription_detection_owner_telegram_user_id"), table_name="subscription_detection")
    op.drop_index(op.f("ix_subscription_detection_email_account_id"), table_name="subscription_detection")
    op.drop_index("idx_sub_detection_owner_status", table_name="subscription_detection")
    op.drop_index("idx_sub_detection_email_status", table_name="subscription_detection")
    op.drop_table("subscription_detection")

    op.drop_index(op.f("ix_subscription_email_account_status"), table_name="subscription_email_account")
    op.drop_index(op.f("ix_subscription_email_account_owner_telegram_user_id"), table_name="subscription_email_account")
    op.drop_index(op.f("ix_subscription_email_account_email_address"), table_name="subscription_email_account")
    op.drop_index("idx_sub_email_owner_status", table_name="subscription_email_account")
    op.drop_table("subscription_email_account")
