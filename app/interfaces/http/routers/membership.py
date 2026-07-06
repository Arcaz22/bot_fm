from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.di import get_membership_repo
from app.domain.membership.rules import resolve_usage_period
from app.infrastructure.db.models import SysTelegramUser
from app.infrastructure.db.repositories.membership import SqlMembershipRepo
from app.interfaces.http.routers.dashboard import get_current_dashboard_user
from app.presentation.schemas.membership import (
    ActiveSubscription,
    AllPlansResponse,
    FeatureUsage,
    PaymentHistoryResponse,
    PaymentItem,
    PlanDetail,
    PlanFeatureDetail,
)

router = APIRouter(prefix="/dashboard/membership", tags=["membership"])


@router.get("/subscription", response_model=ActiveSubscription)
async def get_membership_subscription(
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    membership_repo: SqlMembershipRepo = Depends(get_membership_repo),
):
    """Plan aktif user + sisa kuota per fitur untuk periode berjalan."""
    subscription = await membership_repo.get_active_subscription(current_user.id)
    if not subscription:
        # Pengaman: harusnya tidak pernah kejadian karena /start bot sudah
        # auto-assign free plan, tapi kalau ada data lama, assign sekarang.
        subscription = await membership_repo.ensure_free_subscription(current_user.id)

    plan = subscription.plan
    feature_rows = await membership_repo.list_plan_features(plan.id)

    today = date.today()
    features = []
    for feature in feature_rows:
        period_start, period_end = resolve_usage_period(feature.limit_period, today)
        used = await membership_repo.get_usage(
            current_user.id, feature.feature_key, period_start, period_end
        )
        remaining = None if feature.limit_value is None else max(feature.limit_value - used, 0)
        features.append(
            FeatureUsage(
                feature_key=feature.feature_key,
                is_enabled=feature.is_enabled,
                limit_value=feature.limit_value,
                limit_period=feature.limit_period,
                used=used,
                remaining=remaining,
            )
        )

    return ActiveSubscription(
        plan_code=plan.code,
        plan_name=plan.name,
        price=float(plan.price),
        billing_period=plan.billing_period,
        status=subscription.status,
        started_at=subscription.started_at,
        expires_at=subscription.expires_at,
        is_lifetime=subscription.expires_at is None,
        features=features,
    )


@router.get("/plans", response_model=AllPlansResponse)
async def get_membership_plans(
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    membership_repo: SqlMembershipRepo = Depends(get_membership_repo),
):
    """Katalog semua plan aktif + limit fiturnya masing-masing — buat
    halaman perbandingan/pricing di dashboard."""
    plans = await membership_repo.list_plans_with_features()
    return AllPlansResponse(
        plans=[
            PlanDetail(
                code=plan.code,
                name=plan.name,
                price=float(plan.price),
                billing_period=plan.billing_period,
                features=[
                    PlanFeatureDetail(
                        feature_key=feature.feature_key,
                        is_enabled=feature.is_enabled,
                        limit_value=feature.limit_value,
                        limit_period=feature.limit_period,
                    )
                    for feature in plan.features
                ],
            )
            for plan in plans
        ]
    )


@router.get("/payments", response_model=PaymentHistoryResponse)
async def get_membership_payments(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    membership_repo: SqlMembershipRepo = Depends(get_membership_repo),
):
    """Histori pembayaran user, terbaru dulu."""
    payments = await membership_repo.list_payments(current_user.id, limit=limit)
    return PaymentHistoryResponse(
        payments=[
            PaymentItem(
                id=payment.id,
                plan_code=payment.plan.code,
                plan_name=payment.plan.name,
                provider=payment.provider,
                provider_reference=payment.provider_reference,
                amount=float(payment.amount),
                status=payment.status,
                paid_at=payment.paid_at,
                created_at=payment.created_at,
            )
            for payment in payments
        ]
    )
