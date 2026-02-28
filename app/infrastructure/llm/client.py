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

                Debt-related (hutang-piutang) keys:
                - debt_action (string. One of: "NONE", "BORROW", "LEND", "PAY")
                    - "BORROW"  = user is borrowing money from someone (user becomes debtor)
                    - "LEND"    = user is lending money to someone (user becomes creditor)
                    - "PAY"     = user is paying back an existing debt
                    - "NONE"    = not related to debt
                - counterparty_name (string or null). The other person's name/username, e.g. "Sabil".

                Rules for Indonesian language examples:
                - Phrases like "pinjam 50k ke Sabil", "minjem duit ke Sabil" → debt_action = "BORROW", counterparty_name = "Sabil".
                - Phrases like "pinjemin 50k ke Sabil", "ngasih pinjem 50k ke Sabil" → debt_action = "LEND", counterparty_name = "Sabil".
                - Phrases like "bayar hutang ke Sabil 50k", "lunasin hutang ke Sabil" → debt_action = "PAY", counterparty_name = "Sabil".
                - If there is no clear debt context → debt_action = "NONE" and counterparty_name = null.

                Example 1 (Expense): "Makan 15rb pake gopay"
                Output: {"amount": 15000, "category": "Food", "wallet_name": "Gopay", "transaction_type": "EXPENSE", "description": "Makan", "debt_action": "NONE", "counterparty_name": null}

                Example 2 (Transfer): "Transfer 50rb dari BCA ke Gopay"
                Output: {"amount": 50000, "category": "Transfer", "wallet_name": "BCA", "target_wallet_name": "Gopay", "transaction_type": "TRANSFER", "description": "Topup Gopay", "debt_action": "NONE", "counterparty_name": null}

                Example 3 (Borrowing money): "Pinjam 50k ke Sabil pake BCA"
                Output: {"amount": 50000, "category": "Loan", "wallet_name": "BCA", "transaction_type": "INCOME", "description": "Pinjam dari Sabil", "debt_action": "BORROW", "counterparty_name": "Sabil"}

                Example 4 (Lending money): "Pinjemin 50k ke Sabil dari BCA"
                Output: {"amount": 50000, "category": "Loan", "wallet_name": "BCA", "transaction_type": "EXPENSE", "description": "Pinjemin ke Sabil", "debt_action": "LEND", "counterparty_name": "Sabil"}

                Example 5 (Paying back debt): "Bayar hutang ke Sabil 50k dari BCA"
                Output: {"amount": 50000, "category": "Loan Payment", "wallet_name": "BCA", "transaction_type": "EXPENSE", "description": "Bayar hutang ke Sabil", "debt_action": "PAY", "counterparty_name": "Sabil"}
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

        if context:
            system_prompt += f"\n\nAdditional context from user: {context}"

        try:
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')

            response = await self.model.generate_content_async([
                system_prompt,
                {
                    "mime_type": "image/jpeg",
                    "data": image_base64
                }
            ])

            raw_text = response.text
            logger.debug(f"Gemini Vision raw response: {raw_text}")

            cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()

            return json.loads(cleaned_text)

        except json.JSONDecodeError:
            logger.error(f"Gagal parse JSON dari Gemini Vision: {raw_text}")
            return {"error": "Gagal membaca format data dari AI", "raw": raw_text}
        except Exception as e:
            logger.error(f"Gemini Vision Error: {e}")
            return {"error": str(e)}
