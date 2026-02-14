import logging
from typing import Optional, List
from datetime import datetime

from app.domain.llm.ports import LLMPort
from app.domain.finance.ports import FinanceRepoPort
from app.domain.finance import rules
from app.application.dtos.extraction import ExtractedReceipt, ReceiptContext, ReceiptItem

logger = logging.getLogger(__name__)


class ReceiptService:
    def __init__(self, llm: LLMPort, repo: FinanceRepoPort):
        self.llm = llm
        self.repo = repo

    async def extract_from_image(
        self,
        image_bytes: bytes,
        context: Optional[ReceiptContext] = None
    ) -> dict:
        """
        Extract receipt data from image (untuk testing/preview)
        Belum menyimpan ke database
        """
        # Build context string
        context_str = None
        if context:
            parts = []
            if context.wallet_name:
                parts.append(f"Payment method: {context.wallet_name}")
            if context.default_category:
                parts.append(f"Default category: {context.default_category}")
            if context.notes:
                parts.append(f"Notes: {context.notes}")
            context_str = ". ".join(parts) if parts else None

        # Call LLM Vision
        raw_data = await self.llm.parse_receipt_image(image_bytes, context_str)

        if "error" in raw_data:
            return raw_data

        # Validate dengan Pydantic
        try:
            receipt = ExtractedReceipt(**raw_data)
            return {
                "success": True,
                "data": receipt.model_dump(),
                "context_applied": context.model_dump() if context else None
            }
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {
                "success": False,
                "error": f"Data validation failed: {str(e)}",
                "raw_data": raw_data
            }

    async def process_and_save(
        self,
        user_id: int,
        image_bytes: bytes,
        context: Optional[ReceiptContext] = None
    ) -> str:
        """
        Full flow: Extract dari gambar + Simpan semua item sebagai transaksi
        """
        # 1. Extract data
        result = await self.extract_from_image(image_bytes, context)

        if not result.get("success"):
            return f"❌ Gagal membaca nota: {result.get('error', 'Unknown error')}"

        receipt_data = result["data"]
        wallet_name = context.wallet_name if context else "Cash"

        # 2. Get/Create wallet
        clean_wallet_name = rules.normalize_wallet_name(wallet_name)
        wallet = await self.repo.get_wallet_by_name(user_id, clean_wallet_name)
        if not wallet:
            wallet = await self.repo.create_wallet(user_id, clean_wallet_name)

        # 3. Process each item
        saved_items = []
        total_saved = 0

        items_to_process = receipt_data.get("items", [])

        # Filter items jika user hanya pilih sebagian (split scenario)
        if context and context.selected_items is not None:
            items_to_process = [
                item for idx, item in enumerate(items_to_process)
                if idx in context.selected_items
            ]
            logger.info(f"Split receipt: Processing {len(items_to_process)} of {len(receipt_data.get('items', []))} items")

        for item in items_to_process:
            try:
                # Get/Create category
                cat_name = item.get("category", context.default_category if context else "Uncategorized")
                category = await self.repo.get_category_by_name(user_id, cat_name, "expense")
                if not category:
                    category = await self.repo.create_category(user_id, cat_name, "expense")

                # Calculate total price for item
                item_total = item["price"] * item.get("quantity", 1)

                # Build description dengan context
                description = f"{item['name']} x{item.get('quantity', 1)}"
                if context and context.is_shared and receipt_data.get("store_name"):
                    description += f" (nota bersama - {receipt_data['store_name']})"

                # Create transaction
                transaction_notes = None
                if context and context.notes:
                    transaction_notes = context.notes
                elif context and context.is_shared:
                    total_receipt = receipt_data.get("total", 0)
                    transaction_notes = f"Belanja bersama, total nota {total_receipt:,.0f}, bagian saya {item_total:,.0f}"

                await self.repo.create_transaction(
                    user_id=user_id,
                    wallet_id=wallet.id,
                    category_id=category.id,
                    amount=item_total,
                    type="expense",
                    description=description
                    # TODO: Add notes parameter to create_transaction
                )

                saved_items.append(item["name"])
                total_saved += item_total

            except Exception as e:
                logger.error(f"Error saving item {item}: {e}")
                continue

        # 4. Format response
        store_info = f"🏪 {receipt_data.get('store_name')}\n" if receipt_data.get('store_name') else ""
        items_list = "\n".join([f"  • {name}" for name in saved_items[:5]])
        if len(saved_items) > 5:
            items_list += f"\n  • ... dan {len(saved_items) - 5} item lainnya"

        return (
            f"✅ **Nota Berhasil Dicatat!**\n\n"
            f"{store_info}"
            f"📝 {len(saved_items)} item tercatat:\n{items_list}\n\n"
            f"💰 Total: Rp {total_saved:,.0f}\n"
            f"💳 Wallet: {wallet.name}"
        )
