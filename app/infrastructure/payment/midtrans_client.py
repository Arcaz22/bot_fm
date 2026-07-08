"""
Midtrans Snap client untuk FM service.

Hanya melakukan dua hal:
1. Buat Snap token (create_snap_token) — dipanggil saat user mau checkout.
2. Verifikasi signature webhook (verify_signature) — dipanggil saat Midtrans
   mengirim notifikasi pembayaran.

Tidak ada dependency ke SQLAlchemy atau FastAPI di sini — pure HTTP + crypto.
"""

import hashlib
import logging
from base64 import b64encode

import httpx

logger = logging.getLogger(__name__)

# Base URL Midtrans Snap API
_SNAP_URL = {
    "production": "https://app.midtrans.com/snap/v1/transactions",
    "sandbox":    "https://app.sandbox.midtrans.com/snap/v1/transactions",
}


class MidtransClient:
    def __init__(self, server_key: str, is_production: bool = False):
        self.server_key = server_key
        self.is_production = is_production
        self._snap_url = _SNAP_URL["production" if is_production else "sandbox"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auth_header(self) -> dict:
        """Basic auth: server_key sebagai username, password kosong."""
        token = b64encode(f"{self.server_key}:".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def create_snap_token(
        self,
        order_id: str,
        gross_amount: int,
        plan_name: str,
        customer_name: str,
        customer_email: str | None = None,
        customer_phone: str | None = None,
    ) -> dict:
        """
        Minta Snap token ke Midtrans.

        Returns dict dengan field:
            token     : str  — dipakai frontend untuk buka Snap popup
            redirect_url: str — URL fallback jika tidak pakai popup

        Raises httpx.HTTPStatusError jika Midtrans menolak request.
        """
        payload: dict = {
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": gross_amount,
            },
            "item_details": [
                {
                    "id": order_id,
                    "price": gross_amount,
                    "quantity": 1,
                    "name": plan_name[:50],  # Midtrans max 50 char
                }
            ],
            "customer_details": {
                "first_name": customer_name[:100],
            },
        }

        if customer_email:
            payload["customer_details"]["email"] = customer_email
        if customer_phone:
            payload["customer_details"]["phone"] = customer_phone

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self._snap_url,
                json=payload,
                headers={
                    **self._auth_header(),
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "Midtrans Snap error status=%s body=%s order_id=%s",
                resp.status_code,
                resp.text,
                order_id,
            )
            resp.raise_for_status()

        data = resp.json()
        logger.info("Snap token created order_id=%s", order_id)
        return {
            "token": data.get("token"),
            "redirect_url": data.get("redirect_url"),
        }

    def verify_signature(
        self,
        order_id: str,
        status_code: str,
        gross_amount: str,
        signature_key: str,
    ) -> bool:
        """
        Verifikasi signature webhook Midtrans.

        Formula resmi Midtrans:
            SHA512(order_id + status_code + gross_amount + server_key)

        Returns True jika signature valid, False jika tidak.
        """
        raw = f"{order_id}{status_code}{gross_amount}{self.server_key}"
        expected = hashlib.sha512(raw.encode()).hexdigest()
        valid = expected == signature_key
        if not valid:
            logger.warning(
                "Midtrans signature mismatch order_id=%s expected=%s got=%s",
                order_id,
                expected[:16] + "...",
                signature_key[:16] + "...",
            )
        return valid

    async def get_transaction_status(self, order_id: str) -> dict:
        """
        Ambil status transaksi langsung dari Midtrans API.
        Dipakai untuk double-check saat ada ketidakcocokan webhook.
        """
        base = (
            "https://api.midtrans.com"
            if self.is_production
            else "https://api.sandbox.midtrans.com"
        )
        url = f"{base}/v2/{order_id}/status"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=self._auth_header())

        resp.raise_for_status()
        return resp.json()
