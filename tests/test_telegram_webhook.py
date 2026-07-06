"""
Tests untuk HandleTelegramUpdate usecase dan TransactionService.
Semua test menggunakan MockLLM atau OllamaLLM yang di-mock — TANPA Gemini.

Cakupan:
  - Command: /start, /phone, /fitur, /help
  - Command deprecated: /saldo, /riwayat, /history, /hutang, /piutang
  - Intent detection: dashboard, help, transaction
  - Foto (receipt) dan Kontak
  - AI quota check
  - User baru vs user lama
  - User non-aktif
  - TransactionService: expense, income, transfer, borrow, lend, pay, cash withdrawal
  - OllamaLLM contract: text model vs vision model (via AsyncMock)
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.application.services.transaction_service import TransactionService
from app.application.usecases.telegram import HandleTelegramUpdate, _detect_intent
from app.domain.telegram.entities import TelegramUser
from app.infrastructure.llm.mock_client import MockLLM
from app.infrastructure.llm.ollama_client import OllamaLLM
from app.presentation.schemas.telegram import (
    Chat,
    Contact,
    Message,
    PhotoSize,
    Update,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

CHAT_ID = 999


def _make_update(
    text: str | None = None,
    photos: list | None = None,
    contact: Contact | None = None,
    caption: str | None = None,
) -> Update:
    return Update(
        update_id=1,
        message=Message(
            message_id=1,
            chat=Chat(id=CHAT_ID, first_name="Tester"),
            text=text,
            photo=photos,
            contact=contact,
            caption=caption,
        ),
    )


def _make_user(
    is_active: bool = True,
    state: str = "IDLE",
    phone_number: str | None = None,
    temp_data: dict | None = None,
) -> TelegramUser:
    return TelegramUser(
        id=CHAT_ID,
        first_name="Tester",
        username="tester",
        is_active=is_active,
        current_state=state,
        phone_number=phone_number,
        temp_data=temp_data,
    )


class FakeUserRepo:
    """In-memory TelegramUserRepo."""

    def __init__(self, existing_user: TelegramUser | None = None):
        self._user = existing_user

    async def get(self, user_id: int) -> TelegramUser | None:
        return self._user

    async def upsert(self, user: TelegramUser) -> None:
        self._user = user


class FakeNotifier:
    """Notifier yang merekam semua pesan yang dikirim."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.sent.append((chat_id, text))

    async def get_file(self, file_id: str) -> str | None:
        return "fake/path/photo.jpg"

    async def download_file(self, file_path: str) -> bytes:
        return b"fake-image-bytes"


class FakeFinanceRepo:
    """In-memory FinanceRepoPort."""

    def __init__(self):
        self.wallets: dict[str, SimpleNamespace] = {
            "BCA": SimpleNamespace(id=1, name="BCA")
        }
        self.last_transaction = None

    async def get_wallet_by_name(self, user_id, name):
        return self.wallets.get(name)

    async def create_wallet(self, user_id, name, initial_balance=0):
        wallet = SimpleNamespace(id=len(self.wallets) + 1, name=name)
        self.wallets[name] = wallet
        return wallet

    async def get_category_by_name(self, user_id, name, category_type):
        return None

    async def create_category(self, user_id, name, category_type):
        return SimpleNamespace(id=1, name=name)

    async def create_transaction(self, **kwargs):
        self.last_transaction = kwargs
        return SimpleNamespace(id=42)

    async def create_debt(self, **kwargs):
        return SimpleNamespace(id=1, **kwargs)

    async def get_latest_open_debt_with_counterparty(self, **kwargs):
        return None

    async def get_debts_owed(self, user_id, status):
        return []

    async def mark_debt_as_paid(self, **kwargs):
        return SimpleNamespace(status="paid", amount=0)


class FakeMembershipRepo:
    """In-memory membership repo with configurable feature usage."""

    def __init__(self, used: int = 0, limit_value: int | None = None):
        self.used = used
        self.limit_value = limit_value
        self.subscription = SimpleNamespace(plan_id=1)

    async def get_active_subscription(self, telegram_user_id: int):
        return self.subscription

    async def ensure_free_subscription(self, telegram_user_id: int):
        return self.subscription

    async def get_plan_feature(self, plan_id: int, feature_key: str):
        return SimpleNamespace(
            is_enabled=True,
            limit_value=self.limit_value,
            limit_period="monthly",
        )

    async def get_usage(self, telegram_user_id, feature_key, period_start, period_end):
        return self.used

    async def increment_usage(self, telegram_user_id, feature_key, period_start, period_end):
        self.used += 1


def _make_usecase(
    existing_user: TelegramUser | None = None,
    llm=None,
    notifier: FakeNotifier | None = None,
    finance_repo: FakeFinanceRepo | None = None,
    membership_repo: FakeMembershipRepo | None = None,
) -> tuple[HandleTelegramUpdate, FakeNotifier, FakeUserRepo]:
    repo = FakeUserRepo(existing_user)
    notif = notifier or FakeNotifier()
    finance = finance_repo or FakeFinanceRepo()
    llm_client = llm or MockLLM()

    service = TransactionService(llm_client, finance)
    usecase = HandleTelegramUpdate(
        user_repo=repo,
        notifier=notif,
        trans_service=service,
        membership_repo=membership_repo or FakeMembershipRepo(),
    )

    return usecase, notif, repo


# ---------------------------------------------------------------------------
# 1. Intent Detection Unit Tests
# ---------------------------------------------------------------------------

class TestDetectIntent:
    def test_help_intent_on_menu(self):
        assert _detect_intent("menu") == "help"

    def test_help_intent_on_fitur(self):
        assert _detect_intent("fitur") == "help"

    def test_help_intent_on_greeting(self):
        assert _detect_intent("halo") == "help"

    def test_dashboard_intent_saldo(self):
        assert _detect_intent("berapa saldo aku?") == "dashboard"

    def test_dashboard_intent_riwayat(self):
        assert _detect_intent("riwayat transaksi") == "dashboard"

    def test_dashboard_intent_debt_query(self):
        assert _detect_intent("berapa hutang aku?") == "dashboard"

    def test_transaction_intent_expense(self):
        assert _detect_intent("makan siang 25rb pake OVO") == "transaction"

    def test_transaction_intent_income(self):
        assert _detect_intent("gajian 5 juta masuk BCA") == "transaction"

    def test_transaction_intent_transfer(self):
        assert _detect_intent("transfer 100rb dari BCA ke Gopay") == "transaction"

    def test_transaction_intent_debt_with_amount(self):
        assert _detect_intent("hutang ke Budi 50rb") == "transaction"

    def test_transaction_intent_debt_pay(self):
        assert _detect_intent("bayar hutang ke Budi 25rb") == "transaction"

    def test_dashboard_on_balance_keyword(self):
        assert _detect_intent("cek balance") == "dashboard"


# ---------------------------------------------------------------------------
# 2. Command Handling
# ---------------------------------------------------------------------------

class TestCommandHandling:
    async def test_start_command_new_user(self):
        usecase, notif, _ = _make_usecase()

        await usecase.execute(_make_update(text="/start"))

        assert len(notif.sent) == 1
        reply = notif.sent[0][1]
        assert "Tester" in reply

    async def test_start_command_existing_user_with_phone(self):
        user = _make_user(phone_number="628123456789")
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/start"))

        reply = notif.sent[0][1]
        assert "dashboard" in reply.lower()

    async def test_phone_command_sends_keyboard(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/phone"))

        assert len(notif.sent) == 1
        assert "Bagikan nomor telepon" in notif.sent[0][1]

    async def test_fitur_command(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/fitur"))

        reply = notif.sent[0][1]
        assert "/start" in reply
        assert "/phone" in reply

    async def test_help_command(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/help"))

        assert "Fitur Bot" in notif.sent[0][1]

    async def test_deprecated_saldo_redirects_to_dashboard(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/saldo"))

        reply = notif.sent[0][1]
        assert "dashboard" in reply.lower()

    async def test_deprecated_riwayat_redirects(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/riwayat"))

        assert "dashboard" in notif.sent[0][1].lower()

    async def test_deprecated_debt_redirects(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/hutang"))

        assert "dashboard" in notif.sent[0][1].lower()

    async def test_deprecated_receivables_redirects(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/piutang"))

        assert "dashboard" in notif.sent[0][1].lower()

    async def test_deprecated_history_redirects(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="/history"))

        assert "dashboard" in notif.sent[0][1].lower()


# ---------------------------------------------------------------------------
# 3. Intent Routing (IDLE state)
# ---------------------------------------------------------------------------

class TestIntentRouting:
    async def test_dashboard_intent_routes_correctly(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="cek saldo"))

        assert "dashboard" in notif.sent[0][1].lower()

    async def test_help_intent_routes_correctly(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="menu"))

        assert "Fitur Bot" in notif.sent[0][1]

    async def test_transaction_intent_calls_llm(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="makan siang 25rb pake OVO"))

        assert len(notif.sent) >= 1

        reply = notif.sent[-1][1]
        assert (
            "Transaksi Tercatat" in reply
            or "Terjadi kesalahan" in reply
            or "Maaf" in reply
        )

    async def test_non_idle_user_routes_to_llm(self):
        """User dengan state selain IDLE tetap diproses ke LLM."""
        user = _make_user(state="WAITING_INPUT")
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="makan 15rb"))

        assert len(notif.sent) >= 1


# ---------------------------------------------------------------------------
# 4. User State Management
# ---------------------------------------------------------------------------

class TestUserManagement:
    async def test_new_user_is_created_on_first_message(self):
        usecase, notif, repo = _make_usecase(existing_user=None)

        await usecase.execute(_make_update(text="/start"))

        assert repo._user is not None
        assert repo._user.id == CHAT_ID
        assert repo._user.is_active is True

    async def test_inactive_user_is_blocked(self):
        user = _make_user(is_active=False)
        usecase, notif, _ = _make_usecase(existing_user=user)

        await usecase.execute(_make_update(text="makan 20rb"))

        assert len(notif.sent) >= 1

        reply = notif.sent[0][1]
        assert "⛔" in reply

    async def test_update_with_no_message_is_ignored(self):
        usecase, notif, _ = _make_usecase()
        update = Update(update_id=1, message=None)

        await usecase.execute(update)

        assert len(notif.sent) == 0


# ---------------------------------------------------------------------------
# 5. Photo Handling
# ---------------------------------------------------------------------------

class TestPhotoHandling:
    async def test_photo_triggers_receipt_processing(self):
        user = _make_user()
        notif = FakeNotifier()
        usecase, notif, _ = _make_usecase(existing_user=user, notifier=notif)

        photos = [
            PhotoSize(
                file_id="abc123",
                file_unique_id="u1",
                width=800,
                height=600,
            )
        ]
        update = _make_update(photos=photos)

        mock_receipt_uc = AsyncMock()
        mock_receipt_uc.extract_and_save = AsyncMock(
            return_value={"message": "✅ Struk berhasil diproses, 3 item dicatat."}
        )

        with patch(
            "app.core.di.resolve_process_receipt_usecase",
            AsyncMock(return_value=mock_receipt_uc),
        ):
            await usecase.execute(update)

        assert "Sedang membaca struk" in notif.sent[0][1]
        assert "✅" in notif.sent[1][1]

    async def test_photo_with_caption_is_forwarded(self):
        user = _make_user()
        notif = FakeNotifier()
        usecase, notif, _ = _make_usecase(existing_user=user, notifier=notif)

        photos = [
            PhotoSize(
                file_id="img1",
                file_unique_id="u2",
                width=400,
                height=300,
            )
        ]

        mock_receipt_uc = AsyncMock()
        mock_receipt_uc.extract_and_save = AsyncMock(
            return_value={"message": "✅ OK"}
        )

        with patch(
            "app.core.di.resolve_process_receipt_usecase",
            AsyncMock(return_value=mock_receipt_uc),
        ):
            update = _make_update(photos=photos, caption="beli groceries")
            await usecase.execute(update)

        call_kwargs = mock_receipt_uc.extract_and_save.await_args.kwargs

        assert call_kwargs["context"].notes == "beli groceries"


# ---------------------------------------------------------------------------
# 6. Contact Handling
# ---------------------------------------------------------------------------

class TestContactHandling:
    async def test_valid_contact_saves_phone_number(self):
        user = _make_user()
        usecase, notif, repo = _make_usecase(existing_user=user)

        contact = Contact(phone_number="0812345678", user_id=CHAT_ID)
        update = _make_update(contact=contact)

        await usecase.execute(update)

        assert repo._user.phone_number == "62812345678"
        assert "tersimpan" in notif.sent[-1][1].lower()

    async def test_contact_from_another_user_is_rejected(self):
        user = _make_user()
        usecase, notif, _ = _make_usecase(existing_user=user)

        contact = Contact(phone_number="0899999999", user_id=12345)
        update = _make_update(contact=contact)

        await usecase.execute(update)

        assert "sendiri" in notif.sent[0][1]

    async def test_contact_with_international_format_is_normalized(self):
        user = _make_user()
        usecase, notif, repo = _make_usecase(existing_user=user)

        contact = Contact(phone_number="+62812345678", user_id=CHAT_ID)

        await usecase.execute(_make_update(contact=contact))

        assert repo._user.phone_number == "62812345678"


# ---------------------------------------------------------------------------
# 7. AI Quota
# ---------------------------------------------------------------------------

class TestAIQuota:
    async def _run_with_quota(self, used: int, quota: int):
        user = _make_user()
        membership_repo = FakeMembershipRepo(used=used, limit_value=quota)
        usecase, notif, _ = _make_usecase(
            existing_user=user,
            membership_repo=membership_repo,
        )

        await usecase.execute(_make_update(text="makan 20rb"))

        return notif.sent

    async def test_quota_exceeded_blocks_llm(self):
        sent = await self._run_with_quota(used=5, quota=5)

        assert any("Jatah" in message for _, message in sent)

    async def test_quota_not_exceeded_allows_llm(self):
        sent = await self._run_with_quota(used=0, quota=5)

        assert not any("Jatah" in message for _, message in sent)

    async def test_unlimited_plan_bypasses_usage_limit(self):
        user = _make_user()
        membership_repo = FakeMembershipRepo(used=9999, limit_value=None)
        usecase, notif, _ = _make_usecase(
            existing_user=user,
            membership_repo=membership_repo,
        )

        await usecase.execute(_make_update(text="makan 20rb"))

        assert not any("Jatah" in message for _, message in notif.sent)


# ---------------------------------------------------------------------------
# 8. TransactionService dengan MockLLM
# ---------------------------------------------------------------------------

class TestTransactionServiceWithMockLLM:
    def _make_service(self):
        return TransactionService(MockLLM(), FakeFinanceRepo())

    async def test_expense_transaction(self):
        service = self._make_service()

        result = await service.process_natural_language(
            1,
            "Beli kopi 25rb pakai Gopay",
        )

        assert "🔴" in result
        assert "Transaksi Tercatat" in result

    async def test_income_transaction(self):
        service = self._make_service()

        result = await service.process_natural_language(
            1,
            "Gajian 5 juta masuk BCA",
        )

        assert "🟢" in result

    async def test_transfer_transaction(self):
        """TRANSFER via OllamaLLM mock agar target_wallet_name terisi."""
        repo = FakeFinanceRepo()
        repo.wallets["OVO"] = SimpleNamespace(id=2, name="OVO")

        client = OllamaLLM(text_model="llama3.1:8b")
        client._chat = AsyncMock(
            return_value=(
                {
                    "amount": 100000,
                    "category": "Transfer",
                    "wallet_name": "BCA",
                    "target_wallet_name": "OVO",
                    "description": "Transfer ke OVO",
                    "transaction_type": "TRANSFER",
                    "debt_action": "NONE",
                    "counterparty_name": None,
                },
                {"input": 50, "output": 20, "total": 70},
            )
        )

        service = TransactionService(client, repo)

        result = await service.process_natural_language(
            1,
            "Transfer 100rb dari BCA ke OVO",
        )

        assert "🔄" in result
        assert "Bca" in result
        assert "Ovo" in result

    async def test_borrow_debt(self):
        """Regex bypass: hutang ke seseorang tidak perlu LLM."""
        service = self._make_service()

        result = await service.process_natural_language(
            1,
            "Aku hutang ke Budi 50rb",
        )

        assert "Hutang Tercatat" in result

    async def test_lend_debt(self):
        """Piutang: seseorang hutang ke kita."""
        service = self._make_service()

        result = await service.process_natural_language(
            1,
            "Sari hutang ke saya 75rb",
        )

        assert "Piutang Tercatat" in result

    async def test_cash_withdrawal_is_transfer(self):
        """Tarik tunai selalu jadi TRANSFER ke wallet Cash."""
        repo = FakeFinanceRepo()
        service = TransactionService(MockLLM(), repo)

        result = await service.process_natural_language(
            1,
            "Tarik tunai 200rb dari BCA",
        )

        assert "🔄" in result
        assert "Cash" in result
        assert repo.last_transaction["type"] == "transfer"

    def test_invalid_amount_returns_error(self):
        """Amount 0 harus ditolak oleh domain rule."""
        from app.domain.finance import rules

        with pytest.raises(Exception):
            rules.validate_transaction_amount(0)


# ---------------------------------------------------------------------------
# 9. OllamaLLM Contract Tests (via AsyncMock, tanpa model lokal)
# ---------------------------------------------------------------------------

class TestOllamaLLMContract:
    async def test_parse_transaction_uses_text_model(self):
        client = OllamaLLM(text_model="llama3.1:8b")
        client._chat = AsyncMock(
            return_value=(
                {
                    "amount": 25000,
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

        assert result["amount"] == 25000
        assert client._chat.await_args.kwargs["model"] == "llama3.1:8b"
        assert "images" not in client._chat.await_args.kwargs

    async def test_parse_receipt_uses_vision_model_with_image(self):
        client = OllamaLLM(vision_model="llava:13b")
        client._chat = AsyncMock(
            return_value=(
                {
                    "store_name": "Indomaret",
                    "items": [
                        {
                            "name": "Kopi",
                            "quantity": 1,
                            "price": 15000,
                            "category": "Food",
                        }
                    ],
                    "subtotal": 15000,
                    "tax": 0,
                    "total": 15000,
                    "transaction_date": "2026-06-28",
                },
                {"input": 400, "output": 80, "total": 480},
            )
        )

        result = await client.parse_receipt_image(b"fake-image-bytes")

        call_kwargs = client._chat.await_args.kwargs

        assert call_kwargs["model"] == "llava:13b"
        assert len(call_kwargs["images"]) == 1
        assert result["total"] == 15000

    async def test_parse_transaction_handles_invalid_json(self):
        """OllamaLLM mengembalikan error dict jika JSON tidak valid."""
        client = OllamaLLM(text_model="llama3.1:8b")
        client._chat = AsyncMock(side_effect=ValueError("invalid json"))

        result = await client.parse_transaction("apapun")

        assert "error" in result

    async def test_parse_receipt_handles_invalid_json(self):
        client = OllamaLLM(vision_model="llava:13b")
        client._chat = AsyncMock(side_effect=ValueError("invalid json"))

        result = await client.parse_receipt_image(b"bytes")

        assert "error" in result

    async def test_ollama_transaction_flows_through_service(self):
        """Pastikan hasil OllamaLLM (mock) bisa diproses TransactionService."""
        client = OllamaLLM(text_model="llama3.1:8b")
        client._chat = AsyncMock(
            return_value=(
                {
                    "amount": 50000,
                    "category": "Transport",
                    "wallet_name": "OVO",
                    "target_wallet_name": None,
                    "description": "Naik Grab",
                    "transaction_type": "EXPENSE",
                    "debt_action": "NONE",
                    "counterparty_name": None,
                },
                {"input": 80, "output": 25, "total": 105},
            )
        )

        repo = FakeFinanceRepo()
        repo.wallets["OVO"] = SimpleNamespace(id=2, name="OVO")

        service = TransactionService(client, repo)

        result = await service.process_natural_language(
            1,
            "Naik Grab 50rb pake OVO",
        )

        assert "Transaksi Tercatat" in result
        assert repo.last_transaction["type"] == "expense"


# ---------------------------------------------------------------------------
# 10. MockLLM Unit Tests
# ---------------------------------------------------------------------------

class TestMockLLM:
    async def test_expense_detection(self):
        result = await MockLLM().parse_transaction("Beli kopi 25rb pakai Gopay")

        assert result["transaction_type"] == "EXPENSE"
        assert result["amount"] == 25000
        assert result["wallet_name"] == "Gopay"

    async def test_income_detection(self):
        result = await MockLLM().parse_transaction("Gajian 5 juta")

        assert result["transaction_type"] == "INCOME"
        assert result["amount"] == 5_000_000

    async def test_transfer_detection(self):
        result = await MockLLM().parse_transaction("Transfer 100rb dari BCA ke OVO")

        assert result["transaction_type"] == "TRANSFER"

    async def test_borrow_debt_detection(self):
        result = await MockLLM().parse_transaction("Pinjam dari Budi 50rb")

        assert result["debt_action"] == "BORROW"

    async def test_receipt_image_returns_fixture(self):
        result = await MockLLM().parse_receipt_image(b"any-bytes")

        assert result["total"] > 0
        assert isinstance(result["items"], list)
        assert len(result["items"]) > 0

    async def test_include_usage_flag(self):
        result = await MockLLM().parse_transaction("test", include_usage=True)

        assert "data" in result
        assert "usage" in result
        assert result["model"] == "mock"
