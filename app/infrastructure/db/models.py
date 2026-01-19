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
        CheckConstraint("type IN ('income','expense')", name="ck_category_type"),
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

    embedding_data: Mapped[Optional[list[float]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="transactions")
    wallet: Mapped["MstWallet"] = relationship(foreign_keys=[wallet_id], back_populates="transactions")
    target_wallet: Mapped["MstWallet"] = relationship(foreign_keys=[target_wallet_id])
    category: Mapped["MstCategory"] = relationship()
