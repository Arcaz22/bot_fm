from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.settings import settings
from app.infrastructure.db.models import MbrPlan, MbrPlanFeature, MbrSubscription, MbrUsageCounter


class SqlMembershipRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_subscription(self, telegram_user_id: int) -> Optional[MbrSubscription]:
        stmt = (
            select(MbrSubscription)
            .where(
                MbrSubscription.owner_telegram_user_id == telegram_user_id,
                MbrSubscription.status == "active",
            )
            .order_by(MbrSubscription.started_at.desc())
        )
        result = await self.session.execute(stmt)
        subscriptions = result.scalars().all()

        now = datetime.utcnow()
        for sub in subscriptions:
            if sub.expires_at is None or sub.expires_at > now:
                return sub
        return None

    async def ensure_free_subscription(self, telegram_user_id: int) -> MbrSubscription:
        existing = await self.session.execute(
            select(MbrSubscription).where(
                MbrSubscription.owner_telegram_user_id == telegram_user_id
            )
        )
        if existing.scalars().first():
            # User sudah pernah punya subscription (free atau paid) — jangan
            # timpa. Cukup kembalikan yang aktif kalau ada.
            return await self.get_active_subscription(telegram_user_id)

        free_plan = await self._get_plan_by_code(settings.DEFAULT_FREE_PLAN_CODE)
        if not free_plan:
            raise RuntimeError(
                f"Plan default '{settings.DEFAULT_FREE_PLAN_CODE}' tidak ditemukan. "
                "Jalankan seed plan dulu (scripts/seed_plans.py)."
            )

        subscription = MbrSubscription(
            owner_telegram_user_id=telegram_user_id,
            plan_id=free_plan.id,
            status="active",
            expires_at=None,
        )
        self.session.add(subscription)
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def _get_plan_by_code(self, code: str) -> Optional[MbrPlan]:
        result = await self.session.execute(select(MbrPlan).where(MbrPlan.code == code))
        return result.scalars().first()

    async def get_plan_feature(self, plan_id: int, feature_key: str) -> Optional[MbrPlanFeature]:
        stmt = select(MbrPlanFeature).where(
            MbrPlanFeature.plan_id == plan_id,
            MbrPlanFeature.feature_key == feature_key,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_usage(
        self, telegram_user_id: int, feature_key: str, period_start: date, period_end: date
    ) -> int:
        stmt = select(MbrUsageCounter).where(
            MbrUsageCounter.owner_telegram_user_id == telegram_user_id,
            MbrUsageCounter.feature_key == feature_key,
            MbrUsageCounter.period_start == period_start,
            MbrUsageCounter.period_end == period_end,
        )
        result = await self.session.execute(stmt)
        counter = result.scalars().first()
        return counter.used if counter else 0

    async def increment_usage(
        self, telegram_user_id: int, feature_key: str, period_start: date, period_end: date
    ) -> None:
        # Upsert atomic: insert baris baru used=1, atau kalau baris untuk
        # periode ini sudah ada (unique constraint), tambah 1. Menghindari
        # race condition read-then-write kalau ada 2 request nyaris bersamaan.
        stmt = pg_insert(MbrUsageCounter).values(
            owner_telegram_user_id=telegram_user_id,
            feature_key=feature_key,
            period_start=period_start,
            period_end=period_end,
            used=1,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_usage_counter_period",
            set_={"used": MbrUsageCounter.used + 1, "updated_at": datetime.utcnow()},
        )
        await self.session.execute(stmt)
        await self.session.commit()
