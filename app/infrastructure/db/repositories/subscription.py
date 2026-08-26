from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.db.models import (
    SubDetection,
    SubEmailAccount,
    SubPayment,
    SubSubscription,
)


class SubscriptionRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_connected_email_accounts(self, user_id: int) -> int:
        stmt = select(func.count(SubEmailAccount.id)).where(
            SubEmailAccount.owner_telegram_user_id == user_id,
            SubEmailAccount.status.in_(("connected", "syncing", "needs_reauth", "error")),
        )
        return int((await self.session.execute(stmt)).scalar() or 0)

    async def list_email_accounts(self, user_id: int) -> list[SubEmailAccount]:
        stmt = (
            select(SubEmailAccount)
            .where(SubEmailAccount.owner_telegram_user_id == user_id)
            .order_by(SubEmailAccount.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_email_account(self, user_id: int, account_id: int) -> Optional[SubEmailAccount]:
        stmt = select(SubEmailAccount).where(
            SubEmailAccount.id == account_id,
            SubEmailAccount.owner_telegram_user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_email_account(
        self,
        user_id: int,
        provider: str,
        email_address: str,
        encrypted_access_token: str | None,
        encrypted_refresh_token: str | None,
        scopes: dict | None,
    ) -> SubEmailAccount:
        stmt = select(SubEmailAccount).where(
            SubEmailAccount.owner_telegram_user_id == user_id,
            SubEmailAccount.provider == provider,
            SubEmailAccount.email_address == email_address,
        )
        account = (await self.session.execute(stmt)).scalar_one_or_none()
        if account:
            account.encrypted_access_token = encrypted_access_token
            if encrypted_refresh_token:
                account.encrypted_refresh_token = encrypted_refresh_token
            account.scopes = scopes or {}
            account.status = "connected"
            account.error_message = None
        else:
            account = SubEmailAccount(
                owner_telegram_user_id=user_id,
                provider=provider,
                email_address=email_address,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                scopes=scopes or {},
                status="connected",
            )
            self.session.add(account)

        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def set_email_account_sync_state(
        self,
        account: SubEmailAccount,
        status: str,
        sync_cursor: str | None = None,
        error_message: str | None = None,
    ) -> SubEmailAccount:
        account.status = status
        account.error_message = error_message
        if sync_cursor is not None:
            account.sync_cursor = sync_cursor
        if status == "connected":
            account.last_sync_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def detection_exists(self, email_account_id: int, source_message_id: str) -> bool:
        stmt = select(SubDetection.id).where(
            SubDetection.email_account_id == email_account_id,
            SubDetection.source_message_id == source_message_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def disconnect_email_account(self, user_id: int, account_id: int) -> SubEmailAccount:
        account = await self.get_email_account(user_id, account_id)
        if not account:
            raise ValueError("Email account tidak ditemukan")
        account.status = "disconnected"
        account.encrypted_access_token = None
        account.encrypted_refresh_token = None
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def list_detections(
        self,
        user_id: int,
        status: Optional[str] = None,
        email_account_id: Optional[int] = None,
    ) -> list[SubDetection]:
        filters = [SubDetection.owner_telegram_user_id == user_id]
        if status:
            filters.append(SubDetection.status == status)
        if email_account_id:
            filters.append(SubDetection.email_account_id == email_account_id)

        stmt = (
            select(SubDetection)
            .where(*filters)
            .order_by(SubDetection.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_detection(self, user_id: int, detection_id: int) -> Optional[SubDetection]:
        stmt = select(SubDetection).where(
            SubDetection.id == detection_id,
            SubDetection.owner_telegram_user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_subscriptions(
        self,
        user_id: int,
        status: Optional[str] = None,
        email_account_id: Optional[int] = None,
        due_from: Optional[date] = None,
        due_to: Optional[date] = None,
    ) -> list[SubSubscription]:
        filters = [SubSubscription.owner_telegram_user_id == user_id]
        if status:
            filters.append(SubSubscription.status == status)
        if email_account_id:
            filters.append(SubSubscription.email_account_id == email_account_id)
        if due_from:
            filters.append(SubSubscription.next_billing_date >= due_from)
        if due_to:
            filters.append(SubSubscription.next_billing_date <= due_to)

        stmt = (
            select(SubSubscription)
            .where(*filters)
            .order_by(SubSubscription.next_billing_date.asc().nulls_last(), SubSubscription.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_subscription(self, user_id: int, subscription_id: int) -> Optional[SubSubscription]:
        stmt = (
            select(SubSubscription)
            .options(selectinload(SubSubscription.payments))
            .where(
                SubSubscription.id == subscription_id,
                SubSubscription.owner_telegram_user_id == user_id,
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self, model):
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def commit_refresh(self, model):
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def create_payment(self, payment: SubPayment) -> SubPayment:
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment
