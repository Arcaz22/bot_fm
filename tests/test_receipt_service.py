from app.application.services.receipt_service import ReceiptService
from tests.test_transaction_service import FakeRepo


class GacoanScaledDownReceiptLLM:
    async def parse_receipt_image(self, image_bytes, context=None):
        return {
            "store_name": "GACOAN",
            "items": [
                {"name": "GACOAN COMBAT A", "quantity": 1, "price": 50, "category": "Food"},
                {"name": "MIE GACOAN LEVEL 1", "quantity": 1, "price": 0, "category": "Food"},
                {"name": "UDANG KEJU", "quantity": 1, "price": 0, "category": "Food"},
            ],
            "subtotal": 50,
            "tax": 5,
            "total": 55,
            "transaction_date": "2026-08-05",
        }

    async def interpret_receipt_selection(self, items, caption):
        return {"wallet_name": None, "selected_item_indices": None}


class GacoanMixedScaleReceiptLLM:
    async def parse_receipt_image(self, image_bytes, context=None):
        return {
            "store_name": "GACOAN",
            "items": [
                {"name": "GACOAN COMBAT A", "quantity": 1, "price": 50_000, "category": "Food"},
            ],
            "subtotal": 50_000,
            "tax": 5,
            "total": 55,
            "transaction_date": "2026-08-05",
        }

    async def interpret_receipt_selection(self, items, caption):
        return {"wallet_name": None, "selected_item_indices": None}


class TestReceiptService:
    async def test_receipt_scan_scales_truncated_indonesian_rupiah_amounts(self):
        repo = FakeRepo()
        service = ReceiptService(GacoanScaledDownReceiptLLM(), repo)

        result = await service.process_and_save(123, b"receipt-image")

        assert "Nota Berhasil Dicatat" in result
        assert "Total: Rp 55,000" in result
        assert repo.created_transaction["amount"] == 55_000

    async def test_receipt_scan_uses_subtotal_plus_tax_when_total_is_truncated(self):
        repo = FakeRepo()
        service = ReceiptService(GacoanMixedScaleReceiptLLM(), repo)

        result = await service.process_and_save(123, b"receipt-image")

        assert "Nota Berhasil Dicatat" in result
        assert "Total: Rp 55,000" in result
        assert repo.created_transaction["amount"] == 55_000
