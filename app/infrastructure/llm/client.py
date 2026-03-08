import google.generativeai as genai
import json
import logging
import base64
from typing import Optional, Dict, Any
from app.domain.llm.ports import LLMPort
from app.core.settings import settings

logger = logging.getLogger(__name__)


class GeminiLLM(LLMPort):
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY tidak ditemukan di settings")

        genai.configure(api_key=settings.GOOGLE_API_KEY)

        self.generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.1,
            top_p=0.9,
            max_output_tokens=1024,
        )

        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=self.generation_config
        )

        logger.info(f"GeminiLLM initialized with model: {model_name}")

    async def parse_transaction(self, text: str) -> Dict[str, Any]:
        system_prompt = """
        Ekstrak detail transaksi dari teks bahasa Indonesia. Return JSON dengan field:

        - amount (number): Nominal dalam angka (e.g. 25000, bukan "25rb")
        - category (string): Kategori singkat (Food, Transport, Shopping, Loan, dll)
        - wallet_name (string): Wallet sumber (default: "BCA")
        - target_wallet_name (string|null): Wallet tujuan (hanya untuk TRANSFER)
        - description (string): Deskripsi singkat transaksi
        - transaction_type (string): "EXPENSE", "INCOME", atau "TRANSFER"
        - debt_action (string): "NONE", "BORROW", "LEND", atau "PAY"
        - counterparty_name (string|null): Nama pihak lain (untuk hutang/piutang)

        Aturan Debt:
        - "Pinjam dari X" / "Minjem ke X" → BORROW (user hutang, INCOME)
        - "Pinjemin ke X" / "Kasih pinjam X" → LEND (user piutang, EXPENSE)
        - "Bayar hutang ke X" / "Lunasin X" → PAY (EXPENSE)
        - Tidak ada konteks hutang → NONE

        Contoh:
        - "Beli kopi 25rb pake Gopay" → EXPENSE, amount: 25000, wallet: Gopay
        - "Transfer 50rb BCA ke OVO" → TRANSFER, wallet: BCA, target: OVO
        - "Pinjam 100k dari Budi" → BORROW, INCOME, counterparty: Budi
        - "Bayar hutang ke Sari 50k" → PAY, EXPENSE, counterparty: Sari
        """

        try:
            logger.debug(f"Parsing transaction: '{text}'")

            response = await self.model.generate_content_async(
                f"{system_prompt}\n\nInput User: {text}"
            )

            raw_json = response.text.strip()
            logger.debug(f"Gemini response: {raw_json[:200]}...")

            parsed = json.loads(raw_json)

            required_fields = ["amount", "transaction_type", "debt_action"]
            for field in required_fields:
                if field not in parsed:
                    logger.warning(f"Field '{field}' tidak ada di response AI")
                    parsed[field] = None

            if isinstance(parsed.get("amount"), (int, float)):
                parsed["amount"] = int(parsed["amount"])
            else:
                parsed["amount"] = 0
                logger.warning("Amount tidak valid, diset ke 0")

            parsed.setdefault("wallet_name", "BCA")
            parsed.setdefault("target_wallet_name", None)
            parsed.setdefault("debt_action", "NONE")
            parsed.setdefault("counterparty_name", None)
            parsed.setdefault("category", "Lain-lain")
            parsed.setdefault("description", text[:50])

            logger.info(f"Transaction parsed successfully: {parsed.get('transaction_type')}")
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error: {e}")
            return {
                "error": "Gagal parse format JSON dari AI",
                "transaction_type": "EXPENSE",
                "debt_action": "NONE",
                "amount": 0
            }
        except genai.types.BlockedPromptException as e:
            logger.warning(f"Prompt diblokir oleh Gemini safety filter: {e}")
            return {
                "error": "Konten tidak dapat diproses oleh AI",
                "transaction_type": "EXPENSE",
                "debt_action": "NONE",
                "amount": 0
            }
        except Exception as e:
            logger.error(f"Gemini Error: {type(e).__name__} - {e}")
            raise

    async def parse_receipt_image(
        self,
        image_bytes: bytes,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        system_prompt = """
        Analisis gambar struk/nota dan ekstrak detail transaksi. Return JSON:

        - store_name (string|null): Nama toko/merchant
        - items (array): Daftar item dengan name, quantity, price, category
        - subtotal (number|null): Subtotal sebelum pajak
        - tax (number|null): Pajak (PPN) jika ada
        - total (number): Total akhir (WAJIB)
        - transaction_date (string|null): Tanggal transaksi (YYYY-MM-DD)

        Aturan:
        - Price dalam angka (tanpa "Rp", tanpa titik/strip)
        - Tebak kategori: Food, Grocery, Transport, Shopping, dll
        - Jika total tidak jelas, gunakan jumlah semua item
        - Format tanggal Indonesia: DD/MM/YYYY → YYYY-MM-DD
        """

        if context:
            system_prompt += f"\n\nKonteks tambahan: {context}"

        try:
            logger.debug(f"Parsing receipt image, size: {len(image_bytes)} bytes")

            image_base64 = base64.b64encode(image_bytes).decode('utf-8')

            image_part = {
                "mime_type": "image/jpeg",
                "data": image_base64
            }

            receipt_config = genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
                top_p=0.9,
                max_output_tokens=8192,
            )

            response = await self.model.generate_content_async(
                [system_prompt, image_part],
                generation_config=receipt_config,
            )

            raw_json = response.text.strip()
            logger.debug(f"Gemini Vision response: {raw_json[:200]}...")

            parsed = json.loads(raw_json)

            if "total" not in parsed or parsed["total"] is None:
                logger.warning("Field 'total' tidak ada di response AI")
                parsed["total"] = 0

            if isinstance(parsed.get("total"), (int, float)):
                parsed["total"] = int(parsed["total"])
            else:
                parsed["total"] = 0

            parsed.setdefault("store_name", None)
            parsed.setdefault("items", [])
            parsed.setdefault("subtotal", None)
            parsed.setdefault("tax", None)
            parsed.setdefault("transaction_date", None)

            logger.info(f"Receipt parsed successfully, total: {parsed['total']}")
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error: {e}")
            return {
                "error": "Gagal parse format JSON dari AI Vision",
                "total": 0,
                "items": []
            }
        except genai.types.BlockedPromptException as e:
            logger.warning(f"Image diblokir oleh Gemini safety filter: {e}")
            return {
                "error": "Gambar tidak dapat diproses oleh AI",
                "total": 0,
                "items": []
            }
        except Exception as e:
            logger.error(f"Gemini Vision Error: {type(e).__name__} - {e}")
            return {
                "error": str(e),
                "total": 0,
                "items": []
            }

    async def chat_completion(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        try:
            if system_instruction:
                full_prompt = f"{system_instruction}\n\n{prompt}"
            else:
                full_prompt = prompt

            chat_model = genai.GenerativeModel(
                model_name=self.model.model_name,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    top_p=0.9,
                    max_output_tokens=2048,
                )
            )

            response = await chat_model.generate_content_async(full_prompt)
            return response.text.strip()

        except Exception as e:
            logger.error(f"Chat Completion Error: {e}")
            raise
