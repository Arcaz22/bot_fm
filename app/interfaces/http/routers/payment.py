"""
Payment router — dua endpoint utama:

POST /dashboard/membership/checkout
    Dipanggil dashboard saat user klik tombol upgrade.
    Butuh autentikasi dashboard (JWT via cookie/header).
    Returns Snap token untuk membuka Midtrans popup.

POST /payments/webhook/midtrans
    Dipanggil Midtrans saat status transaksi berubah.
    Tidak butuh autentikasi user — diproteksi via signature verification
    yang dilakukan di dalam PaymentService.handle_webhook().
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.di import get_payment_service
from app.application.services.payment_service import PaymentService
from app.infrastructure.db.models import SysTelegramUser
from app.interfaces.http.routers.dashboard import get_current_dashboard_user
from app.presentation.schemas.payment import CheckoutRequest, CheckoutResponse, MidtransWebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payment"])


# ---------------------------------------------------------------------------
# 1. Checkout — user mulai proses bayar
# ---------------------------------------------------------------------------

@router.post(
    "/dashboard/membership/checkout",
    response_model=CheckoutResponse,
    summary="Inisiasi pembayaran Midtrans Snap",
)
async def create_checkout(
    body: CheckoutRequest,
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    """
    Buat MbrPayment berstatus pending dan dapatkan Snap token Midtrans.

    Frontend memanggil endpoint ini lalu membuka Midtrans Snap popup
    dengan token yang dikembalikan.

    ```js
    const { snap_token } = await fetch('/dashboard/membership/checkout', {
        method: 'POST',
        body: JSON.stringify({ plan_code: 'tier_1' }),
    }).then(r => r.json());

    snap.pay(snap_token, {
        onSuccess: (result) => { /* tampilkan sukses */ },
        onPending: (result) => { /* tampilkan pending */ },
        onError:   (result) => { /* tampilkan error */  },
    });
    ```
    """
    try:
        result = await payment_service.create_checkout(
            telegram_user_id=current_user.id,
            plan_code=body.plan_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Checkout gagal user=%s plan=%s: %s", current_user.id, body.plan_code, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gagal menghubungi Midtrans. Coba beberapa saat lagi.",
        )

    return CheckoutResponse(**result)


# ---------------------------------------------------------------------------
# 2. Webhook Midtrans — notifikasi status transaksi
# ---------------------------------------------------------------------------

@router.post(
    "/payments/webhook/midtrans",
    status_code=status.HTTP_200_OK,
    summary="Midtrans payment notification webhook",
)
async def midtrans_webhook(
    request: Request,
    payment_service: PaymentService = Depends(get_payment_service),
):
    """
    Endpoint untuk menerima notifikasi dari Midtrans.

    Midtrans akan POST ke URL ini setiap kali status transaksi berubah.
    URL ini harus dapat diakses secara publik — daftarkan di Midtrans
    Dashboard → Settings → Configuration → Payment Notification URL.

    Format yang disarankan:
        https://your-domain.com/payments/webhook/midtrans

    Autentikasi dilakukan via signature verification (SHA512), bukan token.
    Tidak ada data sensitif yang dikembalikan ke Midtrans — cukup HTTP 200.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Webhook Midtrans: body bukan JSON valid")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    logger.info("Midtrans webhook received: %s", payload.get("order_id"))

    try:
        result = await payment_service.handle_webhook(payload)
        logger.info("Webhook processed: %s", result)
    except ValueError as e:
        # Signature salah atau format tidak valid — jangan return 2xx
        # supaya Midtrans tidak berpikir webhook berhasil.
        logger.warning("Webhook rejected: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Webhook processing error: %s", e)
        # Return 500 supaya Midtrans retry nanti
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error saat memproses webhook.",
        )

    # Midtrans tidak peduli body response-nya, yang penting HTTP 200
    return {"ok": True}
