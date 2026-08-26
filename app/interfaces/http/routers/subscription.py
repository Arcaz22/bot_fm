from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.di import get_llm_client
from app.domain.llm.ports import LLMPort
from app.infrastructure.db.base import get_db
from app.infrastructure.db.models import SubDetection, SubEmailAccount, SubPayment, SubSubscription, SysTelegramUser
from app.infrastructure.db.repositories.membership import SqlMembershipRepo
from app.infrastructure.db.repositories.subscription import SubscriptionRepo
from app.application.services.subscription_service import SubscriptionService
from app.interfaces.http.routers.dashboard import get_current_dashboard_user
from app.presentation.schemas.subscription import (
    DetectionConfirmRequest,
    DetectionItem,
    DetectionListResponse,
    DetectionStatus,
    DetectionUpdateRequest,
    EmailScanResponse,
    EmailAccountItem,
    EmailAccountListResponse,
    GoogleConnectResponse,
    MarkPaidRequest,
    PaymentItem,
    SubscriptionCreateRequest,
    SubscriptionDetailResponse,
    SubscriptionItem,
    SubscriptionListResponse,
    SubscriptionPageResponse,
    SubscriptionStatus,
    SubscriptionSummaryResponse,
    SubscriptionUpdateRequest,
)


router = APIRouter(prefix="/dashboard/subscriptions", tags=["dashboard-subscriptions"])


def _service(session: AsyncSession, llm: LLMPort | None = None) -> SubscriptionService:
    return SubscriptionService(
        repo=SubscriptionRepo(session),
        membership_repo=SqlMembershipRepo(session),
        llm=llm,
    )


def _email_account_item(account: SubEmailAccount) -> EmailAccountItem:
    return EmailAccountItem(
        id=account.id,
        provider=account.provider,
        email_address=account.email_address,
        status=account.status,
        last_sync_at=account.last_sync_at,
        sync_cursor=account.sync_cursor,
        error_message=account.error_message,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _detection_item(detection: SubDetection) -> DetectionItem:
    return DetectionItem(
        id=detection.id,
        email_account_id=detection.email_account_id,
        source_message_id=detection.source_message_id,
        merchant_name=detection.merchant_name,
        plan_name=detection.plan_name,
        amount=float(detection.amount) if detection.amount is not None else None,
        currency=detection.currency,
        billing_period=detection.billing_period,
        billing_date=detection.billing_date,
        next_billing_date=detection.next_billing_date,
        payment_method=detection.payment_method,
        confidence=float(detection.confidence) if detection.confidence is not None else None,
        status=detection.status,
        raw_subject=detection.raw_subject,
        raw_sender=detection.raw_sender,
        llm_payload=detection.llm_payload,
        created_at=detection.created_at,
        updated_at=detection.updated_at,
    )


def _subscription_item(subscription: SubSubscription) -> SubscriptionItem:
    return SubscriptionItem(
        id=subscription.id,
        email_account_id=subscription.email_account_id,
        merchant_name=subscription.merchant_name,
        plan_name=subscription.plan_name,
        amount=float(subscription.amount),
        currency=subscription.currency,
        billing_period=subscription.billing_period,
        next_billing_date=subscription.next_billing_date,
        wallet_id=subscription.wallet_id,
        category_id=subscription.category_id,
        status=subscription.status,
        source=subscription.source,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
        cancelled_at=subscription.cancelled_at,
    )


def _payment_item(payment: SubPayment) -> PaymentItem:
    return PaymentItem(
        id=payment.id,
        subscription_id=payment.subscription_id,
        transaction_id=payment.transaction_id,
        amount=float(payment.amount),
        currency=payment.currency,
        paid_at=payment.paid_at,
        billing_period_start=payment.billing_period_start,
        billing_period_end=payment.billing_period_end,
        source=payment.source,
        created_at=payment.created_at,
    )


def _summary_response(active_subscriptions: list[SubSubscription]) -> SubscriptionSummaryResponse:
    due_until = date.today() + timedelta(days=14)
    due_soon = [
        item for item in active_subscriptions
        if item.next_billing_date and item.next_billing_date <= due_until
    ]
    return SubscriptionSummaryResponse(
        active_count=len(active_subscriptions),
        monthly_total=sum(_monthly_equivalent(item) for item in active_subscriptions),
        yearly_total=sum(_yearly_equivalent(item) for item in active_subscriptions),
        due_soon=[_subscription_item(item) for item in due_soon],
        trial_ending=[],
    )


@router.get("/email-accounts", response_model=EmailAccountListResponse)
async def list_email_accounts(
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    repo = SubscriptionRepo(session)
    accounts = await repo.list_email_accounts(current_user.id)
    return EmailAccountListResponse(items=[_email_account_item(item) for item in accounts])


@router.post("/email-accounts/connect/google", response_model=GoogleConnectResponse)
async def connect_google_email_account(
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    try:
        await service.ensure_email_account_limit(current_user.id)
        auth_url = service.build_google_auth_url(current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return GoogleConnectResponse(auth_url=auth_url)


@router.get("/email-accounts/oauth/google/callback", response_model=EmailAccountItem)
async def google_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    try:
        account = await service.handle_google_callback(state=state, code=code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return _email_account_item(account)


@router.post("/email-accounts/{email_account_id}/resync", response_model=EmailScanResponse)
async def resync_email_account(
    email_account_id: int,
    max_results: Optional[int] = Query(default=None, ge=1, le=50),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
    llm: LLMPort = Depends(get_llm_client),
):
    service = _service(session, llm)
    try:
        result = await service.scan_email_account(current_user.id, email_account_id, max_results=max_results)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return EmailScanResponse(
        email_account=_email_account_item(result["email_account"]),
        scanned=result["scanned"],
        candidates=result["candidates"],
        detections_created=result["detections_created"],
        detections_skipped=result["detections_skipped"],
    )


@router.delete("/email-accounts/{email_account_id}", response_model=EmailAccountItem)
async def disconnect_email_account(
    email_account_id: int,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    repo = SubscriptionRepo(session)
    try:
        account = await repo.disconnect_email_account(current_user.id, email_account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _email_account_item(account)


@router.get("/detections", response_model=DetectionListResponse)
async def list_detections(
    status: Optional[DetectionStatus] = Query(default=None),
    email_account_id: Optional[int] = Query(default=None),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    repo = SubscriptionRepo(session)
    detections = await repo.list_detections(current_user.id, status, email_account_id)
    return DetectionListResponse(items=[_detection_item(item) for item in detections])


@router.patch("/detections/{detection_id}", response_model=DetectionItem)
async def update_detection(
    detection_id: int,
    payload: DetectionUpdateRequest,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    try:
        detection = await service.update_detection(
            current_user.id,
            detection_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _detection_item(detection)


@router.post("/detections/{detection_id}/confirm", response_model=SubscriptionItem)
async def confirm_detection(
    detection_id: int,
    payload: DetectionConfirmRequest,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    try:
        subscription = await service.confirm_detection(
            current_user.id,
            detection_id,
            subscription_id=payload.subscription_id,
            wallet_id=payload.wallet_id,
            category_id=payload.category_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _subscription_item(subscription)


@router.post("/detections/{detection_id}/ignore", response_model=DetectionItem)
async def ignore_detection(
    detection_id: int,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    try:
        detection = await service.ignore_detection(current_user.id, detection_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _detection_item(detection)


@router.get("/summary", response_model=SubscriptionSummaryResponse)
async def get_subscription_summary(
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    repo = SubscriptionRepo(session)
    active_subscriptions = await repo.list_subscriptions(current_user.id, status="active")
    return _summary_response(active_subscriptions)


@router.get("", response_model=SubscriptionListResponse)
async def list_subscriptions(
    status: Optional[SubscriptionStatus] = Query(default=None),
    email_account_id: Optional[int] = Query(default=None),
    due_from: Optional[date] = Query(default=None),
    due_to: Optional[date] = Query(default=None),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    repo = SubscriptionRepo(session)
    subscriptions = await repo.list_subscriptions(
        current_user.id,
        status=status,
        email_account_id=email_account_id,
        due_from=due_from,
        due_to=due_to,
    )
    return SubscriptionListResponse(items=[_subscription_item(item) for item in subscriptions])


@router.get("/page", response_model=SubscriptionPageResponse)
async def get_subscription_page(
    subscription_status: Optional[SubscriptionStatus] = Query(default=None),
    due_from: Optional[date] = Query(default=None),
    due_to: Optional[date] = Query(default=None),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    repo = SubscriptionRepo(session)
    accounts = await repo.list_email_accounts(current_user.id)
    needs_review = await repo.list_detections(current_user.id, status="needs_review")
    subscriptions = await repo.list_subscriptions(
        current_user.id,
        status=subscription_status,
        due_from=due_from,
        due_to=due_to,
    )
    active_subscriptions = await repo.list_subscriptions(current_user.id, status="active")

    return SubscriptionPageResponse(
        summary=_summary_response(active_subscriptions),
        email_accounts=[_email_account_item(item) for item in accounts],
        needs_review=[_detection_item(item) for item in needs_review],
        subscriptions=[_subscription_item(item) for item in subscriptions],
    )


@router.post("", response_model=SubscriptionItem)
async def create_subscription(
    payload: SubscriptionCreateRequest,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    subscription = await service.create_manual_subscription(
        user_id=current_user.id,
        merchant_name=payload.merchant_name,
        plan_name=payload.plan_name,
        amount=payload.amount,
        currency=payload.currency,
        billing_period=payload.billing_period,
        next_billing_date=payload.next_billing_date,
        wallet_id=payload.wallet_id,
        category_id=payload.category_id,
    )
    return _subscription_item(subscription)


@router.get("/{subscription_id}", response_model=SubscriptionDetailResponse)
async def get_subscription_detail(
    subscription_id: int,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    repo = SubscriptionRepo(session)
    subscription = await repo.get_subscription(current_user.id, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription tidak ditemukan")

    data = _subscription_item(subscription).model_dump()
    data["payments"] = [_payment_item(item) for item in subscription.payments]
    return SubscriptionDetailResponse(**data)


@router.patch("/{subscription_id}", response_model=SubscriptionItem)
async def update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdateRequest,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    try:
        subscription = await service.update_subscription(
            current_user.id,
            subscription_id,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _subscription_item(subscription)


@router.post("/{subscription_id}/mark-paid", response_model=PaymentItem)
async def mark_subscription_paid(
    subscription_id: int,
    payload: MarkPaidRequest,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    try:
        payment = await service.mark_paid(
            current_user.id,
            subscription_id,
            amount=payload.amount,
            paid_at=payload.paid_at,
            billing_period_start=payload.billing_period_start,
            billing_period_end=payload.billing_period_end,
            source=payload.source,
            create_transaction=payload.create_transaction,
            wallet_id=payload.wallet_id,
            category_id=payload.category_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _payment_item(payment)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionItem)
async def cancel_subscription(
    subscription_id: int,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    service = _service(session)
    try:
        subscription = await service.cancel_subscription(current_user.id, subscription_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _subscription_item(subscription)


def _monthly_equivalent(subscription: SubSubscription) -> float:
    amount = float(subscription.amount)
    if subscription.billing_period == "weekly":
        return amount * 52 / 12
    if subscription.billing_period == "monthly":
        return amount
    if subscription.billing_period == "yearly":
        return amount / 12
    return 0


def _yearly_equivalent(subscription: SubSubscription) -> float:
    amount = float(subscription.amount)
    if subscription.billing_period == "weekly":
        return amount * 52
    if subscription.billing_period == "monthly":
        return amount * 12
    if subscription.billing_period == "yearly":
        return amount
    return 0
