from datetime import date
from typing import Optional, Protocol

from app.infrastructure.db.models import MbrPlan, MbrPlanFeature, MbrSubscription


class MembershipRepoPort(Protocol):
    async def ensure_free_subscription(self, telegram_user_id: int) -> MbrSubscription:
        """Idempotent: kalau user belum pernah punya subscription sama sekali,
        buatkan satu ke plan default (settings.DEFAULT_FREE_PLAN_CODE), status
        active, tanpa expires_at (tidak pernah kedaluwarsa). Kalau sudah ada
        subscription apapun (baik masih di free maupun sudah pernah upgrade),
        tidak melakukan apa-apa dan cukup return subscription aktifnya."""
        ...

    async def get_active_subscription(self, telegram_user_id: int) -> Optional[MbrSubscription]:
        """Subscription dengan status='active' dan belum expired (expires_at
        null atau > sekarang). Kalau user punya banyak baris histori, ambil
        yang paling baru."""
        ...

    async def get_plan_feature(self, plan_id: int, feature_key: str) -> Optional[MbrPlanFeature]:
        ...

    async def get_usage(
        self, telegram_user_id: int, feature_key: str, period_start: date, period_end: date
    ) -> int:
        ...

    async def increment_usage(
        self, telegram_user_id: int, feature_key: str, period_start: date, period_end: date
    ) -> None:
        ...
