from pydantic import BaseModel


class CheckoutRequest(BaseModel):
    plan_code: str


class CheckoutResponse(BaseModel):
    payment_id: int
    snap_token: str
    redirect_url: str
    amount: int
    plan_name: str


class MidtransWebhookPayload(BaseModel):
    """
    Field yang selalu dikirim Midtrans di setiap notifikasi.
    Ada field opsional lain tergantung metode bayar, tapi
    yang di sini cukup untuk verifikasi + update status.
    """
    order_id: str
    status_code: str
    gross_amount: str
    signature_key: str
    transaction_status: str
    fraud_status: str | None = None   # hanya ada untuk kartu kredit
    payment_type: str | None = None
    transaction_id: str | None = None

    model_config = {"extra": "allow"}  # Midtrans kirim banyak field ekstra
