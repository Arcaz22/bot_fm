
import logging
from typing import Optional, Dict, Any

from app.domain.llm.ports import LLMPort
from app.domain.finance import category_keywords

logger = logging.getLogger(__name__)


class MockLLM(LLMPort):
    """
    LLM palsu untuk keperluan testing.
    Parse kata kunci sederhana dari teks agar logic service tetap bisa ditest
    tanpa hit API manapun.
    """

    async def parse_transaction(
        self,
        text: str,
        include_usage: bool = False,
    ) -> Dict[str, Any]:
        logger.debug(f"[MockLLM] parse_transaction dipanggil dengan: '{text}'")

        text_lower = text.lower()

        # Deteksi transaction type
        if any(k in text_lower for k in ["tabungan bersama", "patungan", "setoran bersama", "iuran tabungan"]):
            transaction_type = "EXPENSE"
        elif any(k in text_lower for k in ["nabung", "menabung", "tabungan", "investasi", "rdn", "saham", "reksadana", "rekasadana", "stockbit", "ajaib", "crypto", "kripto"]):
            transaction_type = "TRANSFER"
        elif any(k in text_lower for k in ["transfer", "pindah"]):
            transaction_type = "TRANSFER"
        elif any(k in text_lower for k in ["gaji", "gajian", "bonus", "masuk", "terima", "dapat"]):
            transaction_type = "INCOME"
        else:
            transaction_type = "EXPENSE"

        # Deteksi debt action
        if any(k in text_lower for k in ["bayar hutang", "lunasin", "lunas"]):
            debt_action = "PAY"
        elif any(k in text_lower for k in ["pinjam dari", "minjem dari", "hutang ke"]):
            debt_action = "BORROW"
        elif any(k in text_lower for k in ["pinjemin", "pinjamin", "kasih pinjam", "piutang"]):
            debt_action = "LEND"
        else:
            debt_action = "NONE"

        # Deteksi amount sederhana (ambil angka pertama yang ditemukan)
        import re
        amount = 0
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*(rb|ribu|k|jt|juta)?', text_lower)
        if match:
            raw, suffix = match.groups()
            amount = float(raw.replace(",", "."))
            if suffix in {"rb", "ribu", "k"}:
                amount *= 1000
            elif suffix in {"jt", "juta"}:
                amount *= 1_000_000
        amount = int(amount) if amount else 50_000  # default jika tidak ada angka

        # Deteksi wallet
        wallet_map = {
            "gopay": "Gopay", "ovo": "OVO", "dana": "Dana",
            "mandiri": "Mandiri", "bni": "BNI", "bri": "BRI",
            "cash": "Cash", "tunai": "Cash",
            "tabungan": "Tabungan", "rdn": "RDN", "stockbit": "Stockbit",
            "ajaib": "Ajaib", "investasi": "Investasi",
            "crypto": "Crypto", "kripto": "Crypto",
        }
        wallet_name = "BCA"
        for key, name in wallet_map.items():
            if key in text_lower:
                wallet_name = name
                break

        target_wallet_name = None
        if transaction_type == "TRANSFER":
            if "rdn" in text_lower:
                target_wallet_name = "RDN"
            elif any(k in text_lower for k in ["stockbit", "ajaib", "crypto", "kripto"]):
                for key, name in wallet_map.items():
                    if key in text_lower and name != wallet_name:
                        target_wallet_name = name
                        break
            elif any(k in text_lower for k in ["investasi", "saham", "reksadana", "rekasadana"]):
                target_wallet_name = "Investasi"
            elif any(k in text_lower for k in ["nabung", "menabung", "tabungan"]):
                target_wallet_name = "Tabungan"
            else:
                for key, name in wallet_map.items():
                    if key in text_lower and name != wallet_name:
                        target_wallet_name = name
                        break

        # Deteksi kategori
        category_map = {
            "makan": "Food", "minum": "Food", "kopi": "Food", "resto": "Food",
            "bensin": "Transport", "grab": "Transport", "gojek": "Transport",
            "belanja": "Shopping", "beli": "Shopping",
            "gaji": "Salary", "bonus": "Salary",
            "listrik": "Bills", "pulsa": "Bills", "internet": "Bills",
            "tabungan bersama": "Joint Savings", "patungan": "Joint Savings",
            "setoran bersama": "Joint Savings", "iuran tabungan": "Joint Savings",
            "nabung": "Savings", "menabung": "Savings", "tabungan": "Savings",
            "investasi": "Investment", "rdn": "Investment", "saham": "Investment",
            "reksadana": "Investment", "rekasadana": "Investment",
            "stockbit": "Investment", "ajaib": "Investment",
            "crypto": "Investment", "kripto": "Investment",
        }
        category = "Other"
        for key, cat in category_map.items():
            if key in text_lower:
                category = cat
                break
        category = category_keywords.normalize_category(category, transaction_type)

        # Counterparty untuk hutang
        counterparty_name = None
        if debt_action != "NONE":
            name_match = re.search(
                r'(?:ke|dari|sama|kepada)\s+([A-Za-z]+)', text, re.IGNORECASE
            )
            if name_match:
                counterparty_name = name_match.group(1).title()

        result = {
            "amount": amount,
            "category": category,
            "wallet_name": wallet_name,
            "target_wallet_name": target_wallet_name,
            "description": f"[MOCK] {text[:50]}",
            "transaction_type": transaction_type,
            "debt_action": debt_action,
            "counterparty_name": counterparty_name,
        }

        logger.debug(f"[MockLLM] hasil: {result}")
        if include_usage:
            return {"data": result, "usage": {}, "model": "mock"}
        return result

    async def parse_receipt_image(
        self,
        image_bytes: bytes,
        context: Optional[str] = None,
        include_usage: bool = False,
    ) -> Dict[str, Any]:
        logger.debug(f"[MockLLM] parse_receipt_image dipanggil, size: {len(image_bytes)} bytes")

        # Return fixture struk minimarket
        result = {
            "store_name": "Indomaret Mock",
            "items": [
                {"name": "Indomie Goreng", "quantity": 2, "price": 3500, "category": "Grocery"},
                {"name": "Teh Botol", "quantity": 1, "price": 5000, "category": "Food"},
                {"name": "Roti Tawar", "quantity": 1, "price": 12000, "category": "Grocery"},
            ],
            "subtotal": 24000,
            "tax": None,
            "total": 24000,
            "transaction_date": "2025-01-15",
        }
        if include_usage:
            return {"data": result, "usage": {}, "model": "mock"}
        return result

    async def parse_subscription_email(
        self,
        email: dict,
        include_usage: bool = False,
    ) -> Dict[str, Any]:
        text = f"{email.get('subject') or ''} {email.get('snippet') or ''} {email.get('body') or ''}".lower()
        is_subscription = any(
            keyword in text
            for keyword in ["invoice", "receipt", "billing", "renewal", "subscription", "tagihan", "langganan"]
        )
        result = {
            "is_subscription": is_subscription,
            "confidence": 0.85 if is_subscription else 0.2,
            "merchant_name": "Mock Merchant" if is_subscription else None,
            "plan_name": None,
            "amount": 99000 if is_subscription else None,
            "currency": "IDR" if is_subscription else None,
            "billing_period": "monthly" if is_subscription else "unknown",
            "billing_date": None,
            "next_billing_date": None,
            "payment_method": None,
            "status": "active" if is_subscription else "unknown",
            "evidence": "mock",
            "reason": "Mock subscription detection",
        }
        if include_usage:
            return {"data": result, "usage": {}, "model": "mock"}
        return result
