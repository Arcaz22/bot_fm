import base64
import json
import logging
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Dict, Iterator, Optional

import google.generativeai as genai
from langfuse import Langfuse

from app.core.settings import settings
from app.domain.llm.ports import LLMPort

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_langfuse_client() -> Optional[Langfuse]:
    """Create one optional Langfuse client for the application process."""
    if not settings.LANGFUSE_SECRET_KEY or not settings.LANGFUSE_PUBLIC_KEY:
        logger.info("Langfuse monitoring nonaktif: credentials belum dikonfigurasi")
        return None

    try:
        client = Langfuse(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            base_url=settings.LANGFUSE_BASE_URL,
        )
        logger.info("Langfuse monitoring aktif")
        return client
    except Exception:
        # Observability must never make the primary LLM client unavailable.
        logger.exception("Gagal menginisialisasi Langfuse; tracing dinonaktifkan")
        return None


def _usage_details(response: Any) -> Optional[Dict[str, int]]:
    """Translate Gemini usage metadata to Langfuse's normalized token fields."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None

    fields = {
        "input": getattr(usage, "prompt_token_count", None),
        "output": getattr(usage, "candidates_token_count", None),
        "total": getattr(usage, "total_token_count", None),
    }
    normalized = {key: int(value) for key, value in fields.items() if value is not None}
    return normalized or None


def shutdown_langfuse_client() -> None:
    """Flush pending observations when the application process stops."""
    if _get_langfuse_client.cache_info().currsize == 0:
        return

    client = _get_langfuse_client()
    if client is not None:
        client.shutdown()


class GeminiLLM(LLMPort):
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY tidak ditemukan di settings")

        genai.configure(api_key=settings.GOOGLE_API_KEY)

        self.model_name = model_name
        self.generation_parameters = {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_output_tokens": 1024,
            "response_mime_type": "application/json",
        }
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
        self.langfuse = _get_langfuse_client()

        logger.info(f"GeminiLLM initialized with model: {model_name}")

    @contextmanager
    def _observe_generation(
        self,
        *,
        name: str,
        input: Any,
        model_parameters: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        if self.langfuse is None:
            yield None
            return

        with self.langfuse.start_as_current_observation(
            as_type="generation",
            name=name,
            input=input,
            model=self.model_name,
            model_parameters=model_parameters,
            metadata=metadata,
        ) as generation:
            yield generation

    @staticmethod
    def _record_response(generation: Any, response: Any) -> Dict[str, int]:
        usage = _usage_details(response) or {}
        if generation is not None:
            generation.update(
                output=response.text.strip(),
                usage_details=usage or None,
            )
        return usage

    def _result_with_usage(
        self,
        data: Dict[str, Any],
        usage: Dict[str, int],
        include_usage: bool,
    ) -> Dict[str, Any]:
        if not include_usage:
            return data
        return {"data": data, "usage": usage, "model": self.model_name}

    async def parse_transaction(
        self,
        text: str,
        include_usage: bool = False,
    ) -> Dict[str, Any]:
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

        Aturan tarik tunai:
        - "Tarik tunai" / "penarikan tunai" adalah TRANSFER dari wallet sumber
          ke wallet "Cash", bukan EXPENSE.
        - Gunakan category "Cash Withdrawal" dan target_wallet_name "Cash".

        Contoh:
        - "Beli kopi 25rb pake Gopay" → EXPENSE, amount: 25000, wallet: Gopay
        - "Transfer 50rb BCA ke OVO" → TRANSFER, wallet: BCA, target: OVO
        - "Tarik tunai 500rb dari BCA" → TRANSFER, wallet: BCA, target: Cash
        - "Pinjam 100k dari Budi" → BORROW, INCOME, counterparty: Budi
        - "Bayar hutang ke Sari 50k" → PAY, EXPENSE, counterparty: Sari
        """

        usage: Dict[str, int] = {}
        try:
            logger.debug(f"Parsing transaction: '{text}'")

            with self._observe_generation(
                name="gemini.parse_transaction",
                input={
                    "system_instruction": system_prompt.strip(),
                    "user": text,
                },
                model_parameters=self.generation_parameters,
                metadata={"operation": "parse_transaction"},
            ) as generation:
                response = await self.model.generate_content_async(
                    f"{system_prompt}\n\nInput User: {text}"
                )
                usage = self._record_response(generation, response)

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
            return self._result_with_usage(parsed, usage, include_usage)

        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error: {e}")
            data = {
                "error": "Gagal parse format JSON dari AI",
                "transaction_type": "EXPENSE",
                "debt_action": "NONE",
                "amount": 0
            }
            return self._result_with_usage(data, usage, include_usage)
        except genai.types.BlockedPromptException as e:
            logger.warning(f"Prompt diblokir oleh Gemini safety filter: {e}")
            data = {
                "error": "Konten tidak dapat diproses oleh AI",
                "transaction_type": "EXPENSE",
                "debt_action": "NONE",
                "amount": 0
            }
            return self._result_with_usage(data, usage, include_usage)
        except Exception as e:
            logger.error(f"Gemini Error: {type(e).__name__} - {e}")
            raise

    async def parse_receipt_image(
        self,
        image_bytes: bytes,
        context: Optional[str] = None,
        include_usage: bool = False,
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

        usage: Dict[str, int] = {}
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

            receipt_parameters = {
                "temperature": 0.1,
                "top_p": 0.9,
                "max_output_tokens": 8192,
                "response_mime_type": "application/json",
            }
            with self._observe_generation(
                name="gemini.parse_receipt_image",
                input={
                    "system_instruction": system_prompt.strip(),
                    # Do not duplicate a potentially large base64 image in traces.
                    "image": {"mime_type": "image/jpeg", "size_bytes": len(image_bytes)},
                    "context": context,
                },
                model_parameters=receipt_parameters,
                metadata={"operation": "parse_receipt_image"},
            ) as generation:
                response = await self.model.generate_content_async(
                    [system_prompt, image_part],
                    generation_config=receipt_config,
                )
                usage = self._record_response(generation, response)

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
            return self._result_with_usage(parsed, usage, include_usage)

        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error: {e}")
            data = {
                "error": "Gagal parse format JSON dari AI Vision",
                "total": 0,
                "items": []
            }
            return self._result_with_usage(data, usage, include_usage)
        except genai.types.BlockedPromptException as e:
            logger.warning(f"Image diblokir oleh Gemini safety filter: {e}")
            data = {
                "error": "Gambar tidak dapat diproses oleh AI",
                "total": 0,
                "items": []
            }
            return self._result_with_usage(data, usage, include_usage)
        except Exception as e:
            logger.error(f"Gemini Vision Error: {type(e).__name__} - {e}")
            data = {
                "error": str(e),
                "total": 0,
                "items": []
            }
            return self._result_with_usage(data, usage, include_usage)

    async def chat_completion_with_usage(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a test completion and return output plus Gemini token usage."""
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

            chat_parameters = {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_output_tokens": 2048,
            }
            with self._observe_generation(
                name="gemini.chat_completion",
                input={
                    "system_instruction": system_instruction,
                    "user": prompt,
                },
                model_parameters=chat_parameters,
                metadata={"operation": "chat_completion"},
            ) as generation:
                response = await chat_model.generate_content_async(full_prompt)
                usage = self._record_response(generation, response)

            return {
                "output": response.text.strip(),
                "usage": usage,
                "model": self.model_name,
            }

        except Exception as e:
            logger.error(f"Chat Completion Error: {e}")
            raise

    async def chat_completion(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        result = await self.chat_completion_with_usage(prompt, system_instruction)
        return str(result["output"])
