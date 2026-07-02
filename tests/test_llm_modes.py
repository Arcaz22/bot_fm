import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.application.services.transaction_service import TransactionService
from app.infrastructure.llm.mock_client import MockLLM
from app.infrastructure.llm.ollama_client import OllamaLLM


class TestNoNLP:
    """Cepat dan deterministik: tidak menjalankan model AI."""

    async def test_mock_parser_does_not_use_nlp(self):
        result = await MockLLM().parse_transaction("Beli kopi 25rb pakai Gopay")

        assert result["amount"] == 25_000
        assert result["category"] == "Food"
        assert result["wallet_name"] == "Gopay"
        assert result["transaction_type"] == "EXPENSE"

    async def test_debt_regex_bypasses_llm(self):
        llm = SimpleNamespace(parse_transaction=AsyncMock())
        repo = SimpleNamespace(create_debt=AsyncMock())
        service = TransactionService(llm=llm, repo=repo)

        result = await service.process_natural_language(
            user_id=123,
            text="Aku pinjam dari Budi 100rb",
        )

        llm.parse_transaction.assert_not_awaited()
        repo.create_debt.assert_awaited_once()
        assert "Hutang Tercatat" in result


class TestNLPWithOllamaContract:
    """Menguji jalur NLP Ollama tanpa membutuhkan model lokal saat CI."""

    async def test_transaction_uses_llama_text_model(self):
        client = OllamaLLM(text_model="llama3.1:8b")
        client._chat = AsyncMock(
            return_value=(
                {
                    "amount": 25_000,
                    "category": "Food",
                    "wallet_name": "Gopay",
                    "target_wallet_name": None,
                    "description": "Beli kopi",
                    "transaction_type": "EXPENSE",
                    "debt_action": "NONE",
                    "counterparty_name": None,
                },
                {"input": 100, "output": 30, "total": 130},
            )
        )

        result = await client.parse_transaction("Beli kopi 25rb pakai Gopay")

        assert result["amount"] == 25_000
        assert client._chat.await_args.kwargs["model"] == "llama3.1:8b"
        assert "images" not in client._chat.await_args.kwargs


class TestReceiptScanWithOllamaContract:
    """Menguji jalur vision dan memastikan gambar dikirim ke llava."""

    async def test_receipt_scan_uses_llava_vision_model(self):
        client = OllamaLLM(vision_model="llava:13b")
        client._chat = AsyncMock(
            return_value=(
                {
                    "store_name": "Toko Contoh",
                    "items": [
                        {
                            "name": "Kopi",
                            "quantity": 1,
                            "price": 15_000,
                            "category": "Food",
                        }
                    ],
                    "subtotal": 15_000,
                    "tax": 0,
                    "total": 15_000,
                    "transaction_date": "2026-06-28",
                },
                {"input": 400, "output": 80, "total": 480},
            )
        )

        result = await client.parse_receipt_image(b"fake-image-bytes")

        call = client._chat.await_args.kwargs

        assert call["model"] == "llava:13b"
        assert len(call["images"]) == 1
        assert result["total"] == 15_000


@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_TESTS") != "1",
    reason="Set RUN_OLLAMA_TESTS=1 untuk menjalankan model Ollama lokal",
)
class TestOllamaIntegration:
    """Test NLP/vision nyata; sengaja opt-in karena lambat dan butuh model lokal."""

    async def test_real_nlp(self):
        result = await OllamaLLM().parse_transaction(
            "Transfer 50rb dari BCA ke OVO"
        )

        assert "error" not in result
        assert result["amount"] == 50_000
        assert result["transaction_type"] == "TRANSFER"

    async def test_real_receipt_scan(self):
        image_path = os.getenv("OLLAMA_RECEIPT_TEST_IMAGE")

        if not image_path:
            pytest.skip("Set OLLAMA_RECEIPT_TEST_IMAGE ke path gambar nota")

        result = await OllamaLLM().parse_receipt_image(
            Path(image_path).read_bytes()
        )

        assert "error" not in result
        assert result["total"] > 0
        assert isinstance(result["items"], list)
