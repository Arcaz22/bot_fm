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
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    current_state: Mapped[str] = mapped_column(String(50), default="IDLE")
    temp_data: Mapped[Optional[dict]] = mapped_column(JSONB, default={})

    wallets: Mapped[List["MstWallet"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    categories: Mapped[List["MstCategory"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    transactions: Mapped[List["TrsTransaction"]] = relationship(back_populates="owner")

    counterparties: Mapped[List["MstCounterparty"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        foreign_keys="[MstCounterparty.owner_telegram_user_id]"
    )
    debts: Mapped[List["TrsDebt"]] = relationship(back_populates="owner", cascade="all, delete-orphan")

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


class MstCounterparty(Base):
    __tablename__ = "mst_counterparty"
    __table_args__ = (
        UniqueConstraint("owner_telegram_user_id", "display_name", name="uq_counterparty_owner_name"),
        Index("idx_counterparty_owner_name", "owner_telegram_user_id", "display_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_telegram_user_id: Mapped[int] = mapped_column(ForeignKey("sys_telegram_user.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(100))

    # Optional link jika suatu saat counterparty melakukan verifikasi eksplisit.
    linked_telegram_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("sys_telegram_user.id"),
        nullable=True,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["SysTelegramUser"] = relationship(
        back_populates="counterparties",
        foreign_keys=[owner_telegram_user_id]
    )
    linked_user: Mapped[Optional["SysTelegramUser"]] = relationship(foreign_keys=[linked_telegram_user_id])
    debts: Mapped[List["TrsDebt"]] = relationship(back_populates="counterparty")


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
    Model tracking hutang-piutang personal.

    Debt selalu milik satu owner Telegram user. Counterparty adalah kontak/nama
    personal owner, bukan user bot yang wajib ada.

    direction:
    - I_OWE: owner punya hutang ke counterparty
    - THEY_OWE: counterparty punya hutang ke owner
    """
    __tablename__ = "trs_debt"
    __table_args__ = (
        CheckConstraint("status IN ('pending','paid','cancelled')", name="ck_debt_status"),
        CheckConstraint("direction IN ('I_OWE','THEY_OWE')", name="ck_debt_direction"),
        CheckConstraint("amount > 0", name="ck_debt_amount_positive"),
        Index("idx_debt_owner_status", "owner_telegram_user_id", "status"),
        Index("idx_debt_owner_direction_status", "owner_telegram_user_id", "direction", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    owner_telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_telegram_user.id"),
        index=True,
        comment="User pemilik catatan debt"
    )

    counterparty_id: Mapped[int] = mapped_column(
        ForeignKey("mst_counterparty.id"),
        index=True,
        comment="Kontak/nama pihak lawan milik owner"
    )

    direction: Mapped[str] = mapped_column(
        String(20),
        comment="I_OWE | THEY_OWE"
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

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="debts")
    counterparty: Mapped["MstCounterparty"] = relationship(back_populates="debts")
    related_transaction: Mapped[Optional["TrsTransaction"]] = relationship(foreign_keys=[related_transaction_id])

    def __repr__(self):
        return f"<Debt {self.id}: owner={self.owner_telegram_user_id} {self.direction} {self.counterparty_id} {self.amount} ({self.status})>"
