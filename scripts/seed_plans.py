"""
Seed data plan + limit fitur membership. Idempotent — aman dijalankan
berkali-kali (pakai upsert berdasarkan `code` untuk plan, dan
`plan_id + feature_key` untuk plan_feature).

Jalankan manual sekali setelah migration tabel mbr_* dibuat:
    python -m scripts.seed_plans

Sesuaikan feature_key di sini dengan yang benar-benar dicek di kode,
supaya tidak ada typo yang bikin limit tidak pernah kebaca.
"""
import asyncio

from sqlalchemy import select

from app.infrastructure.db.base import async_session
from app.infrastructure.db.models import MbrPlan, MbrPlanFeature

# --- Rename code plan lama -> baru (dijalankan sekali, in-place) ---
# Supaya plan_id yang sudah dipakai di MbrSubscription/MbrPayment lama
# tidak jadi yatim piatu — kita rename baris yang ada, bukan insert baru.
RENAME_MAP = {
    "tier_1": "pro",
    "tier_2": "premium",
}

# --- Definisi plan (harga reguler sesuai dokumen strategi) ---
PLANS = [
    {"code": "free", "name": "Starter", "price": 0, "billing_period": "free"},
    {"code": "pro", "name": "Pro", "price": 19000, "billing_period": "monthly"},
    {"code": "premium", "name": "Premium", "price": 39000, "billing_period": "monthly"},
]

# --- Definisi limit fitur per plan code ---
# limit_value=None berarti unlimited.
# limit_period sekarang "monthly" (sebelumnya "daily") sesuai dokumen strategi.
PLAN_FEATURES = {
    "free": [
        {"feature_key": "ai_parse_transaction", "limit_value": 25, "limit_period": "monthly"},
        {"feature_key": "receipt_scan", "limit_value": 5, "limit_period": "monthly"},
    ],
    "pro": [
        {"feature_key": "ai_parse_transaction", "limit_value": 150, "limit_period": "monthly"},
        {"feature_key": "receipt_scan", "limit_value": 50, "limit_period": "monthly"},
    ],
    "premium": [
        {"feature_key": "ai_parse_transaction", "limit_value": None, "limit_period": None},
        {"feature_key": "receipt_scan", "limit_value": None, "limit_period": None},
    ],
}


async def _rename_existing_codes(session):
    """Rename in-place plan code lama -> baru, kalau baris lama masih ada
    dan baris baru belum ada. Aman dijalankan berkali-kali."""
    for old_code, new_code in RENAME_MAP.items():
        result = await session.execute(select(MbrPlan).where(MbrPlan.code == old_code))
        old_plan = result.scalars().first()
        if not old_plan:
            continue  # sudah pernah di-rename sebelumnya, atau memang belum ada

        result = await session.execute(select(MbrPlan).where(MbrPlan.code == new_code))
        if result.scalars().first():
            continue  # baris baru sudah ada duluan (kondisi tidak wajar, skip demi aman)

        print(f"Rename plan code: {old_code} -> {new_code} (plan_id={old_plan.id} tetap sama)")
        old_plan.code = new_code

    await session.flush()


async def seed_plans():
    async with async_session() as session:
        await _rename_existing_codes(session)

        code_to_plan: dict[str, MbrPlan] = {}

        for plan_data in PLANS:
            result = await session.execute(select(MbrPlan).where(MbrPlan.code == plan_data["code"]))
            plan = result.scalars().first()
            if plan:
                plan.name = plan_data["name"]
                plan.price = plan_data["price"]
                plan.billing_period = plan_data["billing_period"]
                print(f"Update plan: {plan.code}")
            else:
                plan = MbrPlan(**plan_data)
                session.add(plan)
                print(f"Insert plan baru: {plan_data['code']}")
            code_to_plan[plan_data["code"]] = plan

        await session.flush()  # supaya plan.id ke-assign sebelum dipakai di plan_feature

        for code, features in PLAN_FEATURES.items():
            plan = code_to_plan[code]
            for feature_data in features:
                result = await session.execute(
                    select(MbrPlanFeature).where(
                        MbrPlanFeature.plan_id == plan.id,
                        MbrPlanFeature.feature_key == feature_data["feature_key"],
                    )
                )
                feature = result.scalars().first()
                if feature:
                    feature.limit_value = feature_data["limit_value"]
                    feature.limit_period = feature_data["limit_period"]
                else:
                    session.add(
                        MbrPlanFeature(
                            plan_id=plan.id,
                            is_enabled=True,
                            **feature_data,
                        )
                    )

        await session.commit()
        print("Seed plan selesai.")


if __name__ == "__main__":
    asyncio.run(seed_plans())
