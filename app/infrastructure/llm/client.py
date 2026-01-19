import google.generativeai as genai
import json
import logging
from app.domain.llm.ports import LLMPort
from app.core.settings import settings

logger = logging.getLogger(__name__)

class GeminiLLM(LLMPort):
    def __init__(self, model_name="gemini-2.5-flash"):
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
