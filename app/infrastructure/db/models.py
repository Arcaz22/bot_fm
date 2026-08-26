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

    subscriptions: Mapped[List["MbrSubscription"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    usage_counters: Mapped[List["MbrUsageCounter"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    payments: Mapped[List["MbrPayment"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    subscription_email_accounts: Mapped[List["SubEmailAccount"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    subscription_detections: Mapped[List["SubDetection"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    managed_subscriptions: Mapped[List["SubSubscription"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    subscription_payments: Mapped[List["SubPayment"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
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


# =====================================================================
# Membership (plan, subscription, usage quota, payment)
#
# Sengaja TIDAK ada tabel "user" terpisah di sini. Dulu (waktu rencananya
# jadi microservice terpisah dengan DB sendiri) memang perlu identity
# table sendiri karena tidak bisa FK lintas database. Sekarang satu
# database dengan FM, jadi semua tabel membership FK langsung ke
# SysTelegramUser.id supaya cuma ada satu sumber kebenaran untuk "siapa
# user ini" — tidak ada risiko drift antara dua tabel user.
# =====================================================================

class MbrPlan(Base):
    """Daftar tier: free, tier_1, tier_2, dst."""

    __tablename__ = "mbr_plan"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    # code: free, tier_1, tier_2

    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[Numeric] = mapped_column(Numeric(18, 2), default=0)

    billing_period: Mapped[str] = mapped_column(String(20), default="free")
    # billing_period: monthly, yearly, lifetime, free

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    features: Mapped[List["MbrPlanFeature"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[List["MbrSubscription"]] = relationship(back_populates="plan")
    payments: Mapped[List["MbrPayment"]] = relationship(back_populates="plan")

    def __repr__(self):
        return f"<MbrPlan {self.code}>"


class MbrPlanFeature(Base):
    """
    Fitur dan limit tiap plan. Contoh feature_key: receipt_scan,
    ai_parse_transaction, dashboard_export.
    """

    __tablename__ = "mbr_plan_feature"
    __table_args__ = (
        UniqueConstraint("plan_id", "feature_key", name="uq_plan_feature"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    plan_id: Mapped[int] = mapped_column(ForeignKey("mbr_plan.id"), index=True)
    feature_key: Mapped[str] = mapped_column(String(100), index=True)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    limit_value: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    # limit_value: null berarti unlimited

    limit_period: Mapped[Optional[str]] = mapped_column(String(20), default=None)
    # limit_period: daily, monthly, lifetime, atau null

    plan: Mapped["MbrPlan"] = relationship(back_populates="features")

    def __repr__(self):
        return f"<MbrPlanFeature {self.feature_key} @ plan_id={self.plan_id}>"


class MbrSubscription(Base):
    """Subscription user terhadap satu plan, dengan periode aktif."""

    __tablename__ = "mbr_subscription"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_telegram_user_id: Mapped[int] = mapped_column(ForeignKey("sys_telegram_user.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("mbr_plan.id"), index=True)

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # status: active, trialing, expired, cancelled, pending_payment

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="subscriptions")
    plan: Mapped["MbrPlan"] = relationship(back_populates="subscriptions")

    def __repr__(self):
        return f"<MbrSubscription owner={self.owner_telegram_user_id} plan={self.plan_id} status={self.status}>"


class MbrUsageCounter(Base):
    """
    Pemakaian fitur berkuota per periode. Unique constraint memastikan
    satu baris per kombinasi owner + fitur + periode, supaya bisa
    increment dengan aman tanpa duplikasi.
    """

    __tablename__ = "mbr_usage_counter"
    __table_args__ = (
        UniqueConstraint(
            "owner_telegram_user_id", "feature_key", "period_start", "period_end",
            name="uq_usage_counter_period",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_telegram_user_id: Mapped[int] = mapped_column(ForeignKey("sys_telegram_user.id"), index=True)
    feature_key: Mapped[str] = mapped_column(String(100), index=True)

    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)

    used: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="usage_counters")

    def __repr__(self):
        return f"<MbrUsageCounter {self.feature_key} owner={self.owner_telegram_user_id} used={self.used}>"


class MbrPayment(Base):
    """Pembayaran/invoice dari payment provider (manual, midtrans, xendit, dst)."""

    __tablename__ = "mbr_payment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_telegram_user_id: Mapped[int] = mapped_column(ForeignKey("sys_telegram_user.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("mbr_plan.id"), index=True)

    provider: Mapped[str] = mapped_column(String(50))
    # provider: manual, midtrans, xendit

    provider_reference: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True
    )
    # unique supaya webhook yang sama tidak diproses dua kali (idempotent)

    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2))

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # status: pending, paid, failed, expired, refunded

    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="payments")
    plan: Mapped["MbrPlan"] = relationship(back_populates="payments")

    def __repr__(self):
        return f"<MbrPayment {self.id} owner={self.owner_telegram_user_id} status={self.status}>"


# =====================================================================
# Subscription scanner (email account, detection, managed subscription)
# =====================================================================

class SubEmailAccount(Base):
    """Email account yang terhubung untuk scan langganan."""

    __tablename__ = "subscription_email_account"
    __table_args__ = (
        UniqueConstraint(
            "owner_telegram_user_id", "provider", "email_address",
            name="uq_subscription_email_account_owner_provider_email",
        ),
        CheckConstraint("provider IN ('google','microsoft')", name="ck_sub_email_provider"),
        CheckConstraint(
            "status IN ('connected','syncing','needs_reauth','disconnected','error')",
            name="ck_sub_email_status",
        ),
        Index("idx_sub_email_owner_status", "owner_telegram_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_telegram_user.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20), default="google")
    email_address: Mapped[str] = mapped_column(String(255), index=True)

    encrypted_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scopes: Mapped[Optional[dict]] = mapped_column(JSONB, default={})

    status: Mapped[str] = mapped_column(String(20), default="connected", index=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sync_cursor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="subscription_email_accounts")
    detections: Mapped[List["SubDetection"]] = relationship(
        back_populates="email_account", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[List["SubSubscription"]] = relationship(back_populates="email_account")

    def __repr__(self):
        return f"<SubEmailAccount {self.email_address} owner={self.owner_telegram_user_id} status={self.status}>"


class SubDetection(Base):
    """Hasil scan email yang perlu dikonfirmasi user."""

    __tablename__ = "subscription_detection"
    __table_args__ = (
        UniqueConstraint(
            "email_account_id", "source_message_id",
            name="uq_subscription_detection_email_message",
        ),
        CheckConstraint(
            "status IN ('needs_review','confirmed','ignored','merged')",
            name="ck_sub_detection_status",
        ),
        CheckConstraint(
            "billing_period IN ('weekly','monthly','yearly','one_time','unknown')",
            name="ck_sub_detection_billing_period",
        ),
        Index("idx_sub_detection_owner_status", "owner_telegram_user_id", "status"),
        Index("idx_sub_detection_email_status", "email_account_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_telegram_user.id"), index=True
    )
    email_account_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_email_account.id"), index=True
    )
    source_message_id: Mapped[str] = mapped_column(String(255))

    merchant_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    plan_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    amount: Mapped[Optional[Numeric]] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    billing_period: Mapped[str] = mapped_column(String(20), default="unknown")
    billing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_billing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    confidence: Mapped[Optional[Numeric]] = mapped_column(Numeric(5, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="needs_review", index=True)

    raw_subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    raw_sender: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    llm_payload: Mapped[Optional[dict]] = mapped_column(JSONB, default={})

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="subscription_detections")
    email_account: Mapped["SubEmailAccount"] = relationship(back_populates="detections")

    def __repr__(self):
        return f"<SubDetection {self.id} merchant={self.merchant_name} status={self.status}>"


class SubSubscription(Base):
    """Langganan user yang sudah dikonfirmasi atau dibuat manual."""

    __tablename__ = "subscription"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','cancelled','paused','unknown')",
            name="ck_sub_subscription_status",
        ),
        CheckConstraint(
            "billing_period IN ('weekly','monthly','yearly','one_time','unknown')",
            name="ck_sub_subscription_billing_period",
        ),
        CheckConstraint("source IN ('email_scan','manual')", name="ck_sub_subscription_source"),
        Index("idx_sub_subscription_owner_status", "owner_telegram_user_id", "status"),
        Index("idx_sub_subscription_owner_next_billing", "owner_telegram_user_id", "next_billing_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_telegram_user.id"), index=True
    )
    email_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscription_email_account.id"), nullable=True, index=True
    )

    merchant_name: Mapped[str] = mapped_column(String(150))
    plan_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="IDR")
    billing_period: Mapped[str] = mapped_column(String(20), default="monthly")
    next_billing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    wallet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mst_wallet.id"), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mst_category.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="managed_subscriptions")
    email_account: Mapped[Optional["SubEmailAccount"]] = relationship(back_populates="subscriptions")
    wallet: Mapped[Optional["MstWallet"]] = relationship()
    category: Mapped[Optional["MstCategory"]] = relationship()
    payments: Mapped[List["SubPayment"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<SubSubscription {self.id} merchant={self.merchant_name} status={self.status}>"


class SubPayment(Base):
    """Riwayat pembayaran untuk satu langganan."""

    __tablename__ = "subscription_payment"
    __table_args__ = (
        CheckConstraint("source IN ('email_scan','manual','telegram')", name="ck_sub_payment_source"),
        Index("idx_sub_payment_owner_paid_at", "owner_telegram_user_id", "paid_at"),
        Index("idx_sub_payment_subscription_paid_at", "subscription_id", "paid_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    owner_telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_telegram_user.id"), index=True
    )
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscription.id"), index=True)
    transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("trs_transaction.id"), nullable=True, index=True
    )

    amount: Mapped[Numeric] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="IDR")
    paid_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    billing_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    billing_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped["SysTelegramUser"] = relationship(back_populates="subscription_payments")
    subscription: Mapped["SubSubscription"] = relationship(back_populates="payments")
    transaction: Mapped[Optional["TrsTransaction"]] = relationship()

    def __repr__(self):
        return f"<SubPayment {self.id} subscription={self.subscription_id} amount={self.amount}>"
