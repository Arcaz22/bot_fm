from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


BillingPeriod = Literal["weekly", "monthly", "yearly", "one_time", "unknown"]
DetectionStatus = Literal["needs_review", "confirmed", "ignored", "merged"]
EmailAccountStatus = Literal["connected", "syncing", "needs_reauth", "disconnected", "error"]
SubscriptionSource = Literal["email_scan", "manual"]
SubscriptionStatus = Literal["active", "cancelled", "paused", "unknown"]
PaymentSource = Literal["email_scan", "manual", "telegram"]


class EmailAccountItem(BaseModel):
    id: int
    provider: str
    email_address: str
    status: str
    last_sync_at: Optional[datetime]
    sync_cursor: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class EmailAccountListResponse(BaseModel):
    items: list[EmailAccountItem]


class GoogleConnectResponse(BaseModel):
    auth_url: str


class EmailScanResponse(BaseModel):
    email_account: EmailAccountItem
    scanned: int
    candidates: int
    detections_created: int
    detections_skipped: int


class DetectionUpdateRequest(BaseModel):
    merchant_name: Optional[str] = Field(default=None, max_length=150)
    plan_name: Optional[str] = Field(default=None, max_length=150)
    amount: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = Field(default=None, max_length=10)
    billing_period: Optional[BillingPeriod] = None
    billing_date: Optional[date] = None
    next_billing_date: Optional[date] = None
    payment_method: Optional[str] = Field(default=None, max_length=100)


class DetectionItem(BaseModel):
    id: int
    email_account_id: int
    source_message_id: str
    merchant_name: Optional[str]
    plan_name: Optional[str]
    amount: Optional[float]
    currency: Optional[str]
    billing_period: str
    billing_date: Optional[date]
    next_billing_date: Optional[date]
    payment_method: Optional[str]
    confidence: Optional[float]
    status: str
    raw_subject: Optional[str]
    raw_sender: Optional[str]
    llm_payload: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class DetectionListResponse(BaseModel):
    items: list[DetectionItem]


class DetectionConfirmRequest(BaseModel):
    subscription_id: Optional[int] = None
    wallet_id: Optional[int] = None
    category_id: Optional[int] = None


class SubscriptionCreateRequest(BaseModel):
    merchant_name: str = Field(min_length=1, max_length=150)
    plan_name: Optional[str] = Field(default=None, max_length=150)
    amount: float = Field(gt=0)
    currency: str = Field(default="IDR", max_length=10)
    billing_period: BillingPeriod = "monthly"
    next_billing_date: Optional[date] = None
    wallet_id: Optional[int] = None
    category_id: Optional[int] = None


class SubscriptionUpdateRequest(BaseModel):
    merchant_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    plan_name: Optional[str] = Field(default=None, max_length=150)
    amount: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = Field(default=None, max_length=10)
    billing_period: Optional[BillingPeriod] = None
    next_billing_date: Optional[date] = None
    wallet_id: Optional[int] = None
    category_id: Optional[int] = None
    status: Optional[SubscriptionStatus] = None


class SubscriptionItem(BaseModel):
    id: int
    email_account_id: Optional[int]
    merchant_name: str
    plan_name: Optional[str]
    amount: float
    currency: str
    billing_period: str
    next_billing_date: Optional[date]
    wallet_id: Optional[int]
    category_id: Optional[int]
    status: str
    source: str
    created_at: datetime
    updated_at: datetime
    cancelled_at: Optional[datetime]


class SubscriptionListResponse(BaseModel):
    items: list[SubscriptionItem]


class MarkPaidRequest(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    paid_at: Optional[datetime] = None
    billing_period_start: Optional[date] = None
    billing_period_end: Optional[date] = None
    source: PaymentSource = "manual"
    create_transaction: bool = False
    wallet_id: Optional[int] = None
    category_id: Optional[int] = None


class PaymentItem(BaseModel):
    id: int
    subscription_id: int
    transaction_id: Optional[int]
    amount: float
    currency: str
    paid_at: datetime
    billing_period_start: Optional[date]
    billing_period_end: Optional[date]
    source: str
    created_at: datetime


class SubscriptionDetailResponse(SubscriptionItem):
    payments: list[PaymentItem]


class SubscriptionSummaryResponse(BaseModel):
    active_count: int
    monthly_total: float
    yearly_total: float
    due_soon: list[SubscriptionItem]
    trial_ending: list[SubscriptionItem]


class SubscriptionPageResponse(BaseModel):
    summary: SubscriptionSummaryResponse
    email_accounts: list[EmailAccountItem]
    needs_review: list[DetectionItem]
    subscriptions: list[SubscriptionItem]
