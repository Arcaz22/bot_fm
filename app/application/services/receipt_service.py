import logging
from typing import Optional, List
from collections import defaultdict

from app.domain.llm.ports import LLMPort
from app.domain.finance.ports import FinanceRepoPort
from app.domain.finance import rules
from app.domain.finance import category_keywords
from app.domain.finance import receipt_selection
from app.application.dtos.extraction import ExtractedReceipt, ReceiptContext, ReceiptItem

logger = logging.getLogger(__name__)


class ReceiptService:
    def __init__(self, llm: LLMPort, repo: FinanceRepoPort):
        self.llm = llm
        self.repo = repo

    def _normalize_suspicious_rupiah_amounts(self, receipt_data: dict) -> dict:
        """Correct OCR/vision reads like 55.000 -> 55 on Indonesian receipts."""
        money_values: List[float] = []
        for field in ("subtotal", "tax", "total"):
            value = receipt_data.get(field)
            if isinstance(value, (int, float)) and value > 0:
                money_values.append(float(value))

        for item in receipt_data.get("items", []):
            price = item.get("price")
            if isinstance(price, (int, float)) and price > 0:
                money_values.append(float(price))

        if not money_values:
            return receipt_data

        max_amount = max(money_values)
        if 10 <= max_amount < 1000:
            logger.info("Receipt amounts look truncated; scaling rupiah values by 1000")
            for field in ("subtotal", "tax", "total"):
                value = receipt_data.get(field)
                if isinstance(value, (int, float)) and value > 0:
                    receipt_data[field] = value * 1000

            for item in receipt_data.get("items", []):
                price = item.get("price")
                if isinstance(price, (int, float)) and price > 0:
                    item["price"] = price * 1000

        return receipt_data

    def _should_use_receipt_total(
        self,
        all_items: List[dict],
        priced_items: List[dict],
        selected_indices: Optional[List[int]],
        context: Optional[ReceiptContext],
    ) -> bool:
        if selected_indices is not None:
            return False
        if context and context.selected_items is not None:
            return False

        priced_ids = {id(item) for item in priced_items}
        return all(
            item.get("price", 0) <= 0 or id(item) in priced_ids
            for item in all_items
        )

    def _receipt_total_candidate(self, receipt_data: dict, item_sum: float) -> Optional[float]:
        total = receipt_data.get("total")
        if isinstance(total, (int, float)) and total >= item_sum * 0.5:
            return float(total)

        subtotal = receipt_data.get("subtotal")
        tax = receipt_data.get("tax")
        if isinstance(subtotal, (int, float)) and isinstance(tax, (int, float)):
            tax_amount = float(tax)
            if 0 < tax_amount < 1000 <= subtotal:
                tax_amount *= 1000
            subtotal_plus_tax = float(subtotal) + tax_amount
            if subtotal_plus_tax >= item_sum * 0.5:
                return subtotal_plus_tax

        return None

    async def extract_from_image(
        self,
        image_bytes: bytes,
        context: Optional[ReceiptContext] = None
    ) -> dict:
        """
        Extract receipt data dari image (untuk testing/preview).
        Belum menyimpan ke database, belum ada filtering — ini raw
        extraction apa adanya dari vision model.
        """
        # default_category itu structured hint (misal dari dashboard/API),
        # bukan free-text caption, jadi aman diteruskan ke vision prompt.
        context_str = f"Default category: {context.default_category}" if context and context.default_category else None

        raw_data = await self.llm.parse_receipt_image(image_bytes, context_str)

        if "error" in raw_data:
            return raw_data

        try:
            receipt = ExtractedReceipt(**raw_data)
            receipt_data = self._normalize_suspicious_rupiah_amounts(receipt.model_dump())
            return {
                "success": True,
                "data": receipt_data,
                "context_applied": context.model_dump() if context else None
            }
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {
                "success": False,
                "error": f"Data validation failed: {str(e)}",
                "raw_data": raw_data
            }

    async def _resolve_wallet_and_selection(
        self,
        items: List[dict],
        context: Optional[ReceiptContext],
    ) -> tuple[Optional[str], Optional[List[int]]]:
        """3 lapis, dari yang termurah ke yang paling mahal:
        1. context.wallet_name eksplisit (kalau caller struktural set langsung)
        2. regex keyword match ke caption (0 token tambahan)
        3. LLM interpretasi teks (cuma kalau caption ambigu)

        Return (wallet_name atau None, selected_item_indices atau None).
        None untuk selected_item_indices berarti semua item termasuk.
        """
        wallet_name = context.wallet_name if context else None
        selected_indices: Optional[List[int]] = None

        caption = (context.notes if context else None) or ""
        if not caption.strip():
            return wallet_name, selected_indices

        # Lapis 2: regex, 0 token
        if wallet_name is None:
            wallet_name = category_keywords.guess_wallet(caption)

        if receipt_selection.has_restriction_signal(caption):
            direct_match = receipt_selection.match_items_by_name(
                caption, [ReceiptItem(**item) for item in items]
            )
            if direct_match is not None:
                selected_indices = direct_match
                logger.info(f"Item selection resolved via substring match: {direct_match}")
            else:
                # Lapis 3: ambigu, baru panggil LLM (text-only, murah)
                logger.info("Caption ambigu, panggil LLM interpretasi")
                interpretation = await self.llm.interpret_receipt_selection(items, caption)
                if wallet_name is None:
                    wallet_name = interpretation.get("wallet_name")
                selected_indices = interpretation.get("selected_item_indices")

        return wallet_name, selected_indices

    async def process_and_save(
        self,
        user_id: int,
        image_bytes: bytes,
        context: Optional[ReceiptContext] = None
    ) -> str:
        """
        Full flow: Extract dari gambar, filter berdasar context (kalau ada),
        lalu simpan sebagai SATU transaksi agregat (bukan per-item).
        """
        # 1. Extract semua item apa adanya (selalu unconditional, tanpa filter)
        result = await self.extract_from_image(image_bytes, context)

        if not result.get("success"):
            return f"❌ Gagal membaca nota: {result.get('error', 'Unknown error')}"

        receipt_data = result["data"]
        all_items = receipt_data.get("items", [])

        # 2. Resolve wallet + item selection (regex dulu, LLM cuma kalau ambigu)
        wallet_name, selected_indices = await self._resolve_wallet_and_selection(all_items, context)

        items_to_process = all_items
        if selected_indices is not None:
            items_to_process = [item for idx, item in enumerate(all_items) if idx in selected_indices]
            logger.info(f"Receipt filtered: {len(items_to_process)} dari {len(all_items)} item")

        # Legacy: dukung juga context.selected_items (index list eksplisit,
        # dipakai flow split-receipt interaktif kalau ada)
        if context and context.selected_items is not None:
            items_to_process = [
                item for idx, item in enumerate(items_to_process)
                if idx in context.selected_items
            ]

        if not items_to_process:
            return "⚠️ Tidak ada item yang cocok untuk dicatat dari struk ini. Coba cek lagi catatan yang kamu kirim."

        # 3. Exclude item gratis (price 0) dari perhitungan & tampilan —
        # tidak ada nilai finansial, cuma noise.
        priced_items = [item for item in items_to_process if item.get("price", 0) > 0]
        if not priced_items:
            return "⚠️ Semua item yang cocok bernilai Rp 0, tidak ada yang dicatat."

        # 4. Get/Create wallet
        clean_wallet_name = rules.normalize_wallet_name(wallet_name or "Cash")
        wallet = await self.repo.get_wallet_by_name(user_id, clean_wallet_name)
        if not wallet:
            wallet = await self.repo.create_wallet(user_id, clean_wallet_name)

        # 5. Hitung total & kategori dominan (by value) dari item yang disertakan
        item_sum = 0.0
        category_totals: dict[str, float] = defaultdict(float)
        item_names: List[str] = []

        for item in priced_items:
            item_total = item["price"] * item.get("quantity", 1)
            item_sum += item_total
            raw_category = item.get("category") or (context.default_category if context else None)
            cat_name = category_keywords.normalize_category(raw_category, "EXPENSE")
            category_totals[cat_name] += item_total
            item_names.append(f"{item['name']} x{item.get('quantity', 1)}")

        if (
            self._should_use_receipt_total(all_items, priced_items, selected_indices, context)
        ):
            total_amount = self._receipt_total_candidate(receipt_data, item_sum) or item_sum
        else:
            total_amount = item_sum

        dominant_category = max(category_totals, key=category_totals.get)

        category = await self.repo.get_category_by_name(user_id, dominant_category, "expense")
        if not category:
            category = await self.repo.create_category(user_id, dominant_category, "expense")

        # 6. Build description: nama toko + daftar item (dipotong kalau kepanjangan)
        store_name = receipt_data.get("store_name")
        items_desc = ", ".join(item_names[:6])
        if len(item_names) > 6:
            items_desc += f", +{len(item_names) - 6} lainnya"
        description = f"{store_name}: {items_desc}" if store_name else items_desc

        if len(items_to_process) < len(all_items):
            filtered_note = f" (disaring {len(items_to_process)} dari {len(all_items)} item di struk)"
        else:
            filtered_note = ""

        # 7. Simpan SATU transaksi agregat
        await self.repo.create_transaction(
            user_id=user_id,
            wallet_id=wallet.id,
            category_id=category.id,
            amount=total_amount,
            type="expense",
            description=description[:500]
        )

        # 8. Format response
        store_info = f"🏪 {store_name}\n" if store_name else ""
        items_list = "\n".join([f"  • {name}" for name in item_names[:5]])
        if len(item_names) > 5:
            items_list += f"\n  • ... dan {len(item_names) - 5} item lainnya"

        return (
            f"✅ **Nota Berhasil Dicatat!**{filtered_note}\n\n"
            f"{store_info}"
            f"📝 {len(item_names)} item:\n{items_list}\n\n"
            f"💰 Total: Rp {total_amount:,.0f}\n"
            f"🏷️ Kategori: {category.name}\n"
            f"💳 Wallet: {wallet.name}"
        )
