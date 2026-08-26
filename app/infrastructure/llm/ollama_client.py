import base64
import json
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.settings import settings
from app.domain.finance.category_keywords import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    TRANSFER_CATEGORIES,
    normalize_category,
)
from app.domain.llm.ports import LLMPort

logger = logging.getLogger(__name__)


TRANSACTION_PROMPT = """
Ekstrak transaksi dari teks bahasa Indonesia. Balas hanya dengan satu JSON object.

Field wajib:
- amount: number, nominal penuh (25rb menjadi 25000)
- category: string singkat
- wallet_name: string, default BCA
- target_wallet_name: string atau null
- description: string singkat
- transaction_type: EXPENSE, INCOME, atau TRANSFER
- debt_action: NONE, BORROW, LEND, atau PAY
- counterparty_name: string atau null

Aturan:
- Untuk EXPENSE, category wajib salah satu dari: {expense_categories}.
- Untuk INCOME, category wajib salah satu dari: {income_categories}.
- Untuk TRANSFER, category wajib salah satu dari: {transfer_categories}.
- Jangan membuat category baru atau terlalu spesifik. Jika tidak cocok, pakai "Other".
- Liburan/travel/wisata masuk "Other", bukan category baru.
- Transfer antar-wallet dan tarik tunai adalah TRANSFER, bukan EXPENSE.
- Tarik tunai memiliki category "Cash Withdrawal" dan target_wallet_name "Cash".
- Tabungan pribadi/nabung adalah TRANSFER category "Savings" ke target_wallet_name "Tabungan".
- RDN, saham, reksadana, Stockbit, Ajaib, crypto/kripto adalah TRANSFER category "Investment".
- Setor RDN adalah TRANSFER ke target_wallet_name "RDN".
- Investasi saham/reksadana tanpa target eksplisit adalah TRANSFER ke target_wallet_name "Investasi".
- Tabungan bersama/patungan/setoran bersama/iuran tabungan ke orang lain adalah EXPENSE category "Joint Savings".
- Pinjam dari seseorang: BORROW dan INCOME.
- Meminjamkan ke seseorang: LEND dan EXPENSE.
- Bayar hutang: PAY dan EXPENSE.
""".format(
    expense_categories=", ".join(EXPENSE_CATEGORIES),
    income_categories=", ".join(INCOME_CATEGORIES),
    transfer_categories=", ".join(TRANSFER_CATEGORIES),
).strip()


RECEIPT_PROMPT = """
Baca gambar nota dan balas hanya dengan satu JSON object.

Field wajib:
- store_name: string atau null
- items: array object berisi name (string), quantity (integer), price (number), category (string)
- subtotal: number atau null
- tax: number atau null
- total: number
- transaction_date: tanggal YYYY-MM-DD atau null

Gunakan angka tanpa simbol mata uang atau pemisah ribuan. Jika total tidak terbaca,
jumlahkan seluruh item. Harga item adalah harga per unit.
""".strip()


SUBSCRIPTION_EMAIL_PROMPT = """
Ekstrak informasi langganan dari email berikut. Balas hanya JSON object valid.

Aturan:
- is_subscription true hanya jika email berisi invoice, receipt, renewal,
  payment confirmation, trial converting to paid, atau subscription billing.
- Email promo, newsletter, login alert, OTP, diskon, dan rekomendasi produk bukan langganan.
- amount wajib angka penuh tanpa Rp/titik/koma.
- billing_period hanya: monthly, yearly, weekly, one_time, unknown.
- status hanya: active, cancelled, trial, failed_payment, unknown.
- Jika field tidak ada, isi null atau unknown.
- Jangan menebak terlalu jauh. Jika ragu, confidence rendah.

Schema wajib:
{
  "is_subscription": boolean,
  "confidence": number,
  "merchant_name": string|null,
  "plan_name": string|null,
  "amount": number|null,
  "currency": string|null,
  "billing_period": "monthly"|"yearly"|"weekly"|"one_time"|"unknown",
  "billing_date": "YYYY-MM-DD"|null,
  "next_billing_date": "YYYY-MM-DD"|null,
  "payment_method": string|null,
  "status": "active"|"cancelled"|"trial"|"failed_payment"|"unknown",
  "evidence": string,
  "reason": string
}
""".strip()


class OllamaLLM(LLMPort):
    """LLM lokal melalui Ollama: model teks dan vision dapat dikonfigurasi terpisah."""

    def __init__(
        self,
        base_url: str | None = None,
        text_model: str | None = None,
        vision_model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.text_model = text_model or settings.OLLAMA_TEXT_MODEL
        self.vision_model = vision_model or settings.OLLAMA_VISION_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT_SECONDS

    async def _chat(
        self,
        *,
        model: str,
        prompt: str,
        images: list[str] | None = None,
    ) -> tuple[Dict[str, Any], Dict[str, int]]:
        message: Dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            message["images"] = images

        payload = {
            "model": model,
            "messages": [message],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()

        body = response.json()
        content = body.get("message", {}).get("content", "")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Respons Ollama harus berupa JSON object")

        input_tokens = int(body.get("prompt_eval_count") or 0)
        output_tokens = int(body.get("eval_count") or 0)
        usage = {
            "input": input_tokens,
            "output": output_tokens,
            "total": input_tokens + output_tokens,
        }
        return parsed, usage

    @staticmethod
    def _with_usage(
        data: Dict[str, Any],
        usage: Dict[str, int],
        model: str,
        include_usage: bool,
    ) -> Dict[str, Any]:
        if include_usage:
            return {"data": data, "usage": usage, "model": model}
        return data

    async def parse_transaction(
        self,
        text: str,
        include_usage: bool = False,
    ) -> Dict[str, Any]:
        try:
            data, usage = await self._chat(
                model=self.text_model,
                prompt=f"{TRANSACTION_PROMPT}\n\nTeks transaksi: {text}",
            )
            data["amount"] = int(data.get("amount") or 0)
            data.setdefault("category", "Other")
            data.setdefault("wallet_name", "BCA")
            data.setdefault("target_wallet_name", None)
            data.setdefault("description", text[:50])
            data.setdefault("transaction_type", "EXPENSE")
            data.setdefault("debt_action", "NONE")
            data.setdefault("counterparty_name", None)
            data["category"] = normalize_category(
                data.get("category"),
                data.get("transaction_type"),
            )
            return self._with_usage(data, usage, self.text_model, include_usage)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Respons JSON Ollama text tidak valid: %s", exc)
            data = {
                "error": "Gagal parse format JSON dari Ollama",
                "amount": 0,
                "transaction_type": "EXPENSE",
                "debt_action": "NONE",
            }
            return self._with_usage(data, {}, self.text_model, include_usage)

    async def parse_receipt_image(
        self,
        image_bytes: bytes,
        context: Optional[str] = None,
        include_usage: bool = False,
    ) -> Dict[str, Any]:
        prompt = RECEIPT_PROMPT
        if context:
            prompt += f"\n\nKonteks tambahan: {context}"

        try:
            image = base64.b64encode(image_bytes).decode("ascii")
            data, usage = await self._chat(
                model=self.vision_model,
                prompt=prompt,
                images=[image],
            )
            data["total"] = int(data.get("total") or 0)
            data.setdefault("store_name", None)
            data.setdefault("items", [])
            data.setdefault("subtotal", None)
            data.setdefault("tax", None)
            data.setdefault("transaction_date", None)
            return self._with_usage(data, usage, self.vision_model, include_usage)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Respons JSON Ollama vision tidak valid: %s", exc)
            data = {
                "error": "Gagal parse format JSON dari Ollama Vision",
                "total": 0,
                "items": [],
            }
            return self._with_usage(data, {}, self.vision_model, include_usage)

    async def parse_subscription_email(
        self,
        email: dict,
        include_usage: bool = False,
    ) -> Dict[str, Any]:
        prompt = (
            f"{SUBSCRIPTION_EMAIL_PROMPT}\n\n"
            f"Email:\n"
            f"Subject: {email.get('subject') or ''}\n"
            f"From: {email.get('sender') or ''}\n"
            f"Date: {email.get('date') or ''}\n"
            f"Snippet/Body: {(email.get('body') or email.get('snippet') or '')[:4000]}"
        )
        try:
            data, usage = await self._chat(model=self.text_model, prompt=prompt)
            return self._with_usage(_normalize_subscription_result(data), usage, self.text_model, include_usage)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Respons JSON Ollama subscription tidak valid: %s", exc)
            data = _normalize_subscription_result({})
            data["reason"] = "Gagal parse format JSON dari Ollama"
            return self._with_usage(data, {}, self.text_model, include_usage)


def _normalize_subscription_result(data: Dict[str, Any]) -> Dict[str, Any]:
    billing_period = data.get("billing_period") or "unknown"
    if billing_period not in {"monthly", "yearly", "weekly", "one_time", "unknown"}:
        billing_period = "unknown"

    status = data.get("status") or "unknown"
    if status not in {"active", "cancelled", "trial", "failed_payment", "unknown"}:
        status = "unknown"

    amount = data.get("amount")
    if not isinstance(amount, (int, float)):
        amount = None

    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0

    return {
        "is_subscription": bool(data.get("is_subscription")),
        "confidence": max(0, min(float(confidence), 1)),
        "merchant_name": data.get("merchant_name"),
        "plan_name": data.get("plan_name"),
        "amount": amount,
        "currency": data.get("currency"),
        "billing_period": billing_period,
        "billing_date": data.get("billing_date"),
        "next_billing_date": data.get("next_billing_date"),
        "payment_method": data.get("payment_method"),
        "status": status,
        "evidence": data.get("evidence") or "unknown",
        "reason": data.get("reason") or "",
    }
