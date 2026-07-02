
import logging
from typing import Optional, Dict, Any

from app.domain.llm.ports import LLMPort

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
        if any(k in text_lower for k in ["transfer", "pindah"]):
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
        }
        wallet_name = "BCA"
        for key, name in wallet_map.items():
            if key in text_lower:
                wallet_name = name
                break

        target_wallet_name = None
        if transaction_type == "TRANSFER":
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
        }
        category = "Lain-lain"
        for key, cat in category_map.items():
            if key in text_lower:
                category = cat
                break

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
