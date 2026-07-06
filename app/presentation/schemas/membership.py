from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class FeatureUsage(BaseModel):
    feature_key: str
    is_enabled: bool
    limit_value: Optional[int]   # None = unlimited
    limit_period: Optional[str]  # daily / monthly / lifetime / None
    used: int
    remaining: Optional[int]     # None = unlimited


class ActiveSubscription(BaseModel):
    plan_code: str
    plan_name: str
    price: float
    billing_period: str
    status: str
    started_at: datetime
    expires_at: Optional[datetime]  # None = lifetime, tidak pernah expired
    is_lifetime: bool
    features: List[FeatureUsage]


class PlanFeatureDetail(BaseModel):
    feature_key: str
    is_enabled: bool
    limit_value: Optional[int]
    limit_period: Optional[str]


class PlanDetail(BaseModel):
    code: str
    name: str
    price: float
    billing_period: str
    features: List[PlanFeatureDetail]


class AllPlansResponse(BaseModel):
    plans: List[PlanDetail]


class PaymentItem(BaseModel):
    id: int
    plan_code: str
    plan_name: str
    provider: str
    provider_reference: Optional[str]
    amount: float
    status: str
    paid_at: Optional[datetime]
    created_at: datetime


class PaymentHistoryResponse(BaseModel):
    payments: List[PaymentItem]
