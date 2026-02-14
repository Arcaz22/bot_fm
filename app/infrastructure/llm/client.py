import google.generativeai as genai
import json
import logging
import base64
from typing import Optional
from app.domain.llm.ports import LLMPort
from app.core.settings import settings

logger = logging.getLogger(__name__)

class GeminiLLM(LLMPort):
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(model_name)

    async def parse_transaction(self, text: str) -> dict:
        system_prompt = """
        You are a financial assistant. Extract transaction details from the user text.
        Return ONLY valid JSON with these keys:
        - amount (number)
        - category (string, short category name. e.g. "Food", "Transport")
        - wallet_name (string. The SOURCE wallet. e.g. "BCA", "Cash". Default "BCA")
        - target_wallet_name (string. ONLY for TRANSFER. The DESTINATION wallet. e.g. "Gopay", "Bibit")
        - description (string, what did they buy? or "Transfer to Gopay")
        - transaction_type (string. "EXPENSE", "INCOME", or "TRANSFER")

        Example 1 (Expense): "Makan 15rb pake gopay"
        Output: {"amount": 15000, "category": "Food", "wallet_name": "Gopay", "transaction_type": "EXPENSE", "description": "Makan"}

        Example 2 (Transfer): "Transfer 50rb dari BCA ke Gopay"
        Output: {"amount": 50000, "category": "Transfer", "wallet_name": "BCA", "target_wallet_name": "Gopay", "transaction_type": "TRANSFER", "description": "Topup Gopay"}
        """

        full_prompt = f"{system_prompt}\n\nUser Text: {text}"

        try:
            response = await self.model.generate_content_async(full_prompt)
            raw_text = response.text

            cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()

            return json.loads(cleaned_text)

        except json.JSONDecodeError:
            logger.error(f"Gagal parse JSON dari Gemini: {raw_text}")
            return {"error": "Gagal membaca format data dari AI"}
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            raise e

    async def parse_receipt_image(self, image_bytes: bytes, context: Optional[str] = None) -> dict:
        """
        Parse receipt/nota image menggunakan Gemini Vision API

        Args:
            image_bytes: Raw bytes dari gambar
            context: Konteks tambahan dari user (misal: "bayar pake BCA", "belanja bulanan")
        """
        system_prompt = """
        You are a receipt/nota OCR expert. Analyze the receipt image and extract all transaction details.

        Return ONLY valid JSON with this structure:
        {
            "store_name": "Nama toko/merchant (string atau null)",
            "items": [
                {
                    "name": "Nama item",
                    "quantity": 1,
                    "price": 15000,
                    "category": "Food/Grocery/Transport/etc"
                }
            ],
            "subtotal": 50000,
            "tax": 5000,
            "total": 55000,
            "transaction_date": "2024-01-20"
        }

        Rules:
        1. Extract ALL items from the receipt
        2. Price should be in number format (no currency symbol)
        3. Guess appropriate category for each item (Food, Grocery, Drink, Snack, Household, etc)
        4. If date is not visible, set transaction_date to null
        5. If tax is not visible, set tax to null
        6. Total is REQUIRED - this is the final amount paid

        Common Indonesian receipt patterns:
        - "Rp", "IDR" = Indonesian Rupiah
        - "QTY" = Quantity
        - "TOTAL", "GRAND TOTAL", "JUMLAH" = Total amount
        - "PPN", "TAX" = Tax
        """

        # Tambahkan context dari user jika ada
        if context:
            system_prompt += f"\n\nAdditional context from user: {context}"

        try:
            # Encode image to base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')

            # Buat content dengan image
            response = await self.model.generate_content_async([
                system_prompt,
                {
                    "mime_type": "image/jpeg",
                    "data": image_base64
                }
            ])

            raw_text = response.text
            logger.debug(f"Gemini Vision raw response: {raw_text}")

            # Clean dan parse JSON
            cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()

            return json.loads(cleaned_text)

        except json.JSONDecodeError:
            logger.error(f"Gagal parse JSON dari Gemini Vision: {raw_text}")
            return {"error": "Gagal membaca format data dari AI", "raw": raw_text}
        except Exception as e:
            logger.error(f"Gemini Vision Error: {e}")
            return {"error": str(e)}
