"""
PaymentService — orchestrator antara Midtrans dan membership DB.

Tanggung jawab:
1. Membuat order (MbrPayment pending) + Snap token.
2. Memproses webhook Midtrans:
   - Verifikasi signature.
   - Update status MbrPayment.
   - Aktifkan/perpanjang MbrSubscription jika payment paid.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.settings import settings
from app.infrastructure.db.models import MbrPayment, MbrPlan, MbrSubscription, SysTelegramUser
from app.infrastructure.payment.midtrans_client import MidtransClient

logger = logging.getLogger(__name__)

# Durasi subscription per billing_period plan (dalam hari)
_BILLING_DAYS: dict[str, int | None] = {
    "monthly":  30,
    "yearly":   365,
    "lifetime": None,   # None = tidak expired
    "free":     None,
}


def _build_order_id(payment_id: int) -> str:
    """order_id harus unik dan bisa di-parse balik ke payment_id."""
    return f"FM-PAY-{payment_id}"


def _parse_payment_id(order_id: str) -> int | None:
    """Balik dari order_id ke payment_id. Return None jika format tidak cocok."""
    try:
        prefix = "FM-PAY-"
        if not order_id.startswith(prefix):
            return None
        return int(order_id[len(prefix):])
    except (ValueError, AttributeError):
        return None


class PaymentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.midtrans = MidtransClient(
            server_key=settings.MIDTRANS_SERVER_KEY,
            is_production=settings.MIDTRANS_IS_PRODUCTION,
        )

    # ------------------------------------------------------------------
    # 1. Checkout: buat payment pending + ambil Snap token
    # ------------------------------------------------------------------

    async def create_checkout(
        self,
        telegram_user_id: int,
        plan_code: str,
    ) -> dict:
        """
        Buat MbrPayment berstatus pending, lalu minta Snap token ke Midtrans.

        Returns:
            {
                "payment_id": int,
                "snap_token": str,      # untuk Snap popup di dashboard
                "redirect_url": str,    # fallback URL
                "amount": int,
                "plan_name": str,
            }

        Raises:
            ValueError jika plan tidak ditemukan atau tidak aktif.
            httpx.HTTPStatusError jika Midtrans gagal.
        """
        # 1. Ambil plan
        plan = await self._get_plan(plan_code)
        if not plan:
            raise ValueError(f"Plan '{plan_code}' tidak ditemukan atau tidak aktif.")

        amount = int(plan.price)  # Midtrans butuh integer (Rupiah, no decimal)
        if amount <= 0:
            raise ValueError(f"Plan '{plan_code}' gratis, tidak perlu checkout.")

        # 2. Ambil nama user untuk customer_details
        user = await self._get_user(telegram_user_id)
        customer_name = user.first_name if user else "User"
        customer_phone = user.phone_number if user else None

        # 3. Buat MbrPayment dengan status pending terlebih dulu
        #    supaya kita punya payment_id untuk order_id Midtrans.
        payment = MbrPayment(
            owner_telegram_user_id=telegram_user_id,
            plan_id=plan.id,
            provider="midtrans",
            amount=amount,
            status="pending",
        )
        self.session.add(payment)
        await self.session.flush()   # dapat payment.id tanpa commit dulu
        await self.session.refresh(payment)

        order_id = _build_order_id(payment.id)
        payment.provider_reference = order_id
        await self.session.commit()

        logger.info(
            "Checkout created payment_id=%s order_id=%s user=%s plan=%s amount=%s",
            payment.id, order_id, telegram_user_id, plan_code, amount,
        )

        # 4. Minta Snap token ke Midtrans
        snap = await self.midtrans.create_snap_token(
            order_id=order_id,
            gross_amount=amount,
            plan_name=f"FM {plan.name}",
            customer_name=customer_name,
            customer_phone=customer_phone,
        )

        return {
            "payment_id": payment.id,
            "snap_token": snap["token"],
            "redirect_url": snap["redirect_url"],
            "amount": amount,
            "plan_name": plan.name,
        }

    # ------------------------------------------------------------------
    # 2. Webhook: terima notifikasi dari Midtrans
    # ------------------------------------------------------------------

    async def handle_webhook(self, payload: dict) -> dict:
        """
        Proses notifikasi webhook Midtrans.

        Idempotent: kalau payment_id yang sama datang dua kali dengan
        status yang sama, tidak ada perubahan state ganda.

        Returns dict ringkasan aksi yang dilakukan (untuk logging).
        Raises ValueError jika payload tidak valid / signature salah.
        """
        order_id        = payload.get("order_id", "")
        status_code     = payload.get("status_code", "")
        gross_amount    = payload.get("gross_amount", "")
        signature_key   = payload.get("signature_key", "")
        transaction_status = payload.get("transaction_status", "")
        fraud_status    = payload.get("fraud_status", "")

        logger.info(
            "Webhook received order_id=%s transaction_status=%s fraud=%s",
            order_id, transaction_status, fraud_status,
        )

        # 1. Verifikasi signature
        if not self.midtrans.verify_signature(order_id, status_code, gross_amount, signature_key):
            raise ValueError(f"Signature Midtrans tidak valid untuk order_id={order_id}")

        # 2. Parse payment_id dari order_id
        payment_id = _parse_payment_id(order_id)
        if payment_id is None:
            raise ValueError(f"Format order_id tidak dikenali: {order_id}")

        # 3. Ambil payment dari DB
        payment = await self._get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment id={payment_id} tidak ditemukan di DB.")

        # 4. Tentukan status baru
        new_status = self._resolve_payment_status(transaction_status, fraud_status)

        # 5. Idempotency: skip kalau status tidak berubah
        if payment.status == new_status:
            logger.info("Webhook idempotent, status tidak berubah: %s", new_status)
            return {"action": "skipped", "reason": "status_same", "payment_id": payment_id}

        old_status = payment.status
        payment.status = new_status

        if new_status == "paid":
            payment.paid_at = datetime.utcnow()
            await self._activate_subscription(payment)

        await self.session.commit()

        logger.info(
            "Payment updated payment_id=%s %s -> %s",
            payment_id, old_status, new_status,
        )

        return {
            "action": "updated",
            "payment_id": payment_id,
            "old_status": old_status,
            "new_status": new_status,
        }

    # ------------------------------------------------------------------
    # 3. Aktivasi subscription setelah paid
    # ------------------------------------------------------------------

    async def _activate_subscription(self, payment: MbrPayment) -> None:
        """
        Cancel subscription aktif yang ada, lalu buat subscription baru
        sesuai plan yang baru dibayar.

        Kalau user perpanjang plan yang sama sebelum expired, expires_at
        dilanjutkan dari expires_at lama (tidak dari sekarang).
        """
        plan = await self._get_plan_by_id(payment.plan_id)
        if not plan:
            logger.error("Plan id=%s tidak ditemukan saat aktivasi.", payment.plan_id)
            return

        billing_days = _BILLING_DAYS.get(plan.billing_period)
        telegram_user_id = payment.owner_telegram_user_id

        # Ambil subscription aktif yang ada
        existing = await self._get_active_subscription(telegram_user_id)

        now = datetime.utcnow()

        # Hitung expires_at baru
        if billing_days is None:
            new_expires_at = None   # lifetime
        else:
            # Kalau ada subscription aktif dan belum expired, lanjutkan dari sana
            if existing and existing.expires_at and existing.expires_at > now:
                base = existing.expires_at
            else:
                base = now
            new_expires_at = base + timedelta(days=billing_days)

        # Cancel subscription lama
        if existing:
            existing.status = "cancelled"
            existing.cancelled_at = now

        # Buat subscription baru
        new_sub = MbrSubscription(
            owner_telegram_user_id=telegram_user_id,
            plan_id=payment.plan_id,
            status="active",
            started_at=now,
            expires_at=new_expires_at,
        )
        self.session.add(new_sub)

        logger.info(
            "Subscription activated user=%s plan=%s expires_at=%s",
            telegram_user_id, plan.code, new_expires_at,
        )

    # ------------------------------------------------------------------
    # Helpers private
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_payment_status(transaction_status: str, fraud_status: str) -> str:
        """
        Terjemahkan transaction_status + fraud_status Midtrans
        ke status internal MbrPayment.

        Referensi: https://docs.midtrans.com/docs/payment-notifications
        """
        if transaction_status in ("capture",):
            # Kartu kredit: challenge kalau fraud_status=challenge
            if fraud_status == "challenge":
                return "pending"
            return "paid"

        if transaction_status == "settlement":
            return "paid"

        if transaction_status in ("deny", "cancel", "failure"):
            return "failed"

        if transaction_status == "expire":
            return "expired"

        if transaction_status == "refund":
            return "refunded"

        # pending, authorize, dll — tetap pending
        return "pending"

    async def _get_plan(self, code: str) -> MbrPlan | None:
        result = await self.session.execute(
            select(MbrPlan).where(MbrPlan.code == code, MbrPlan.is_active.is_(True))
        )
        return result.scalars().first()

    async def _get_plan_by_id(self, plan_id: int) -> MbrPlan | None:
        result = await self.session.execute(
            select(MbrPlan).where(MbrPlan.id == plan_id)
        )
        return result.scalars().first()

    async def _get_user(self, telegram_user_id: int) -> SysTelegramUser | None:
        result = await self.session.execute(
            select(SysTelegramUser).where(SysTelegramUser.id == telegram_user_id)
        )
        return result.scalars().first()

    async def _get_payment(self, payment_id: int) -> MbrPayment | None:
        result = await self.session.execute(
            select(MbrPayment).where(MbrPayment.id == payment_id)
        )
        return result.scalars().first()

    async def _get_active_subscription(self, telegram_user_id: int) -> MbrSubscription | None:
        result = await self.session.execute(
            select(MbrSubscription)
            .where(
                MbrSubscription.owner_telegram_user_id == telegram_user_id,
                MbrSubscription.status == "active",
            )
            .order_by(MbrSubscription.started_at.desc())
        )
        subs = result.scalars().all()
        now = datetime.utcnow()
        for sub in subs:
            if sub.expires_at is None or sub.expires_at > now:
                return sub
        return None
