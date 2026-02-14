from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint, func, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from datetime import datetime, date

from app.infrastructure.db.base import Base

class SysTelegramUser(Base):
    __tablename__ = "sys_telegram_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    first_name: Mapped[str] = mapped_column(String(100))
    username: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    current_state: Mapped[str] = mapped_column(String(50), default="IDLE")
    temp_data: Mapped[Optional[dict]] = mapped_column(JSONB, default={})

    wallets: Mapped[List["MstWallet"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    categories: Mapped[List["MstCategory"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    transactions: Mapped[List["TrsTransaction"]] = relationship(back_populates="owner")

    # Hutang-piutang relationships
    debts_owed: Mapped[List["TrsDebt"]] = relationship(
        back_populates="debtor",
        foreign_keys="[TrsDebt.debtor_user_id]"
    )
    debts_to_collect: Mapped[List["TrsDebt"]] = relationship(
        back_populates="creditor",
        foreign_keys="[TrsDebt.creditor_user_id]"
    )

    def __repr__(self):
        return f"<User {self.id} - {self.first_name}>"


class MstWallet(Base):
    __tablename__ = "mst_wallet"
    __table_args__ = (
        UniqueConstraint("owner_telegram_user_id", "name", name="uq_wallet_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_telegram_user_id: Mapped[int] = mapped_column(ForeignKey("sys_telegram_user.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(20), default="general")

    initial_balance: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="wallets")
    transactions: Mapped[List["TrsTransaction"]] = relationship(
        back_populates="wallet",
        foreign_keys="[TrsTransaction.wallet_id]"
    )

class MstCategory(Base):
    __tablename__ = "mst_category"
    __table_args__ = (
        UniqueConstraint("owner_telegram_user_id", "name", "type", name="uq_cat_user_name_type"),

        CheckConstraint("type IN ('income','expense','transfer')", name="ck_category_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_telegram_user_id: Mapped[int] = mapped_column(ForeignKey("sys_telegram_user.id"), index=True)

    name: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(10))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="categories")


class TrsTransaction(Base):
    __tablename__ = "trs_transaction"
    __table_args__ = (
        CheckConstraint("type IN ('income','expense','transfer')", name="ck_trx_type"),
        Index("idx_trx_owner_date", "owner_telegram_user_id", "trx_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_telegram_user_id: Mapped[int] = mapped_column(ForeignKey("sys_telegram_user.id"), index=True)

    wallet_id: Mapped[int] = mapped_column(ForeignKey("mst_wallet.id"), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mst_category.id"), nullable=True)

    target_wallet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mst_wallet.id"), nullable=True)

    trx_date: Mapped[date] = mapped_column(Date, default=func.current_date())
    type: Mapped[str] = mapped_column(String(10)) # income, expense, transfer
    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="transactions")
    wallet: Mapped["MstWallet"] = relationship(foreign_keys=[wallet_id], back_populates="transactions")
    target_wallet: Mapped["MstWallet"] = relationship(foreign_keys=[target_wallet_id])
    category: Mapped["MstCategory"] = relationship()


class TrsDebt(Base):
    """
    Model untuk tracking hutang-piutang

    Scenarios:
    1. User A bayar dulu untuk User B → User B ngutang ke User A
       - creditor_user_id = A (yang bayar/kasih pinjaman)
       - debtor_user_id = B (yang hutang)

    2. User A upload nota, tapi sebagian item untuk User B
       - A create debt: B harus bayar ke A
    """
    __tablename__ = "trs_debt"
    __table_args__ = (
        CheckConstraint("status IN ('pending','paid','cancelled')", name="ck_debt_status"),
        CheckConstraint("amount > 0", name="ck_debt_amount_positive"),
        Index("idx_debt_debtor_status", "debtor_user_id", "status"),
        Index("idx_debt_creditor_status", "creditor_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Creditor = Yang ngasih pinjaman / bayar duluan
    creditor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sys_telegram_user.id"),
        index=True,
        comment="User yang bayar duluan (punya piutang)"
    )

    # Debtor = Yang ngutang / harus bayar
    debtor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sys_telegram_user.id"),
        index=True,
        comment="User yang ngutang (punya hutang)"
    )

    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    description: Mapped[str] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        comment="pending | paid | cancelled"
    )

    # Optional: Link ke transaction jika ada
    related_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("trs_transaction.id"),
        nullable=True,
        comment="Transaction ID jika ada pembayaran via transfer"
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    creditor: Mapped["SysTelegramUser"] = relationship(
        back_populates="debts_to_collect",
        foreign_keys=[creditor_user_id]
    )
    debtor: Mapped["SysTelegramUser"] = relationship(
        back_populates="debts_owed",
        foreign_keys=[debtor_user_id]
    )
    related_transaction: Mapped[Optional["TrsTransaction"]] = relationship(foreign_keys=[related_transaction_id])

    def __repr__(self):
        return f"<Debt {self.id}: {self.debtor_user_id} owes {self.creditor_user_id} {self.amount} ({self.status})>"

