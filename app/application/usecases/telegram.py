import logging
import re
from typing import Set

from app.application.services.transaction_service import TransactionService
from app.presentation.schemas.telegram import Update, Message
from app.domain.telegram.entities import TelegramUser
from app.domain.telegram.rules import ensure_active, reset_to_idle
from app.domain.telegram.ports import TelegramUserRepo, TelegramNotifier
from app.core.settings import settings
from app.core.di import resolve_manage_debt_usecase, resolve_process_receipt_usecase

logger = logging.getLogger(__name__)


def _detect_intent(text: str) -> str:
    """
    Hybrid Intent Detection dengan prioritas eksplisit:
    1. History (frasa spesifik)
    2. Debt (dengan konteks query vs action)
    3. Balance (dengan negative lookahead)
    4. Transaction (default fallback ke LLM)

    Menggunakan token-based matching untuk menghindari false positive substring.
    """
    text_lower = text.lower().strip()

    tokens: Set[str] = set(re.findall(r'\b[a-z0-9]+\b', text_lower))

    HISTORY_PHRASES = [
        "riwayat", "history", "histori", "catatan transaksi",
        "5 terakhir", "transaksi terakhir", "transaksi sebelumnya"
    ]

    DEBT_KEYWORDS = {"hutang", "utang", "piutang", "berhutang", "berutang"}
    DEBT_QUERY_CTX = {"berapa", "cek", "lihat", "sisa", "daftar", "list", "ada", "punya"}
    DEBT_ACTION_CTX = {"bayar", "lunas", "lunasin", "setor", "kirim", "transfer"}

    BALANCE_KEYWORDS = {
        "saldo", "balance", "duit", "uang", "kekayaan", "dana",
        "aset", "asset", "punya berapa", "sisa berapa"
    }
    BALANCE_NEGATIVE = {
        "beli", "bayar", "transfer", "kirim", "masuk", "keluar",
        "topup", "deposit", "tarik", "withdraw"
    }

    # 1. PRIORITAS 1: History (frasa spesifik paling eksplisit)
    if any(phrase in text_lower for phrase in HISTORY_PHRASES):
        logger.debug(f"Intent HISTORY detected by phrase match: '{text}'")
        return "history"

    # 2. PRIORITAS 2: Debt Logic
    has_debt_keyword = bool(tokens & DEBT_KEYWORDS)

    if has_debt_keyword:
        has_action = bool(tokens & DEBT_ACTION_CTX)
        has_query = bool(tokens & DEBT_QUERY_CTX)

        if has_action:
            logger.debug(f"Intent TRANSACTION detected: debt payment action '{text}'")
            return "transaction"
        elif has_query or len(tokens) <= 4:
            logger.debug(f"Intent DEBT detected by query context: '{text}'")
            return "debt"
        logger.debug(f"Intent TRANSACTION detected: debt keyword ambiguous '{text}'")
        return "transaction"

    # 3. PRIORITAS 3: Balance Logic (dengan Negative Lookahead)
    has_balance_keyword = bool(tokens & BALANCE_KEYWORDS)
    has_negative_ctx = bool(tokens & BALANCE_NEGATIVE)

    if has_balance_keyword:
        if has_negative_ctx:
            logger.debug(f"Intent TRANSACTION detected: balance keyword excluded by context '{text}'")
            return "transaction"
        else:
            logger.debug(f"Intent BALANCE detected: '{text}'")
            return "balance"

    # 4. PRIORITAS 4: History (single word fallback)
    if any(kw in tokens for kw in {"riwayat", "history", "histori"}):
        logger.debug(f"Intent HISTORY detected by single word fallback: '{text}'")
        return "history"

    # 5. DEFAULT: Transaction (LLM Fallback)
    logger.debug(f"Intent TRANSACTION detected as default fallback: '{text}'")
    return "transaction"


class HandleTelegramUpdate:
    def __init__(
        self,
        user_repo: TelegramUserRepo,
        notifier: TelegramNotifier,
        trans_service: TransactionService
    ):
        self.user_repo = user_repo
        self.notifier = notifier
        self.trans_service = trans_service

    async def _check_ai_quota(self, user: TelegramUser) -> bool:
        """Cek kuota penggunaan AI untuk user non-whitelist."""
        if user.id in settings.ai_whitelist_ids:
            return True

        temp = user.temp_data or {}
        try:
            used = int(temp.get("ai_usage", 0) or 0)
        except (TypeError, ValueError):
            used = 0

        quota = settings.AI_FREE_QUOTA

        if quota and quota > 0 and used >= quota:
            await self.notifier.send_message(
                user.id,
                (
                    "⚠️ Jatah penggunaan AI Anda sudah habis.\n\n"
                    "Hubungi admin jika ingin menambah limit atau dimasukkan ke whitelist."
                ),
            )
            return False

        temp["ai_usage"] = used + 1
        user.temp_data = temp
        await self.user_repo.upsert(user)
        return True

    async def _handle_photo(self, msg, user: TelegramUser, chat_id: int) -> None:
        """Handle pesan foto — proses sebagai struk belanja."""
        from app.application.dtos.extraction import ReceiptContext

        await self.notifier.send_message(chat_id, "📸 Sedang membaca struk, tunggu sebentar...")

        # Ambil foto resolusi tertinggi (terakhir di array)
        largest_photo = msg.photo[-1]
        file_path = await self.notifier.get_file(largest_photo.file_id)
        if not file_path:
            await self.notifier.send_message(chat_id, "❌ Gagal mengunduh foto dari Telegram.")
            return

        image_bytes = await self.notifier.download_file(file_path)
        if not image_bytes:
            await self.notifier.send_message(chat_id, "❌ Gagal mengunduh foto.")
            return

        caption = (msg.caption or "").strip()
        context = ReceiptContext(notes=caption) if caption else None

        usecase = await resolve_process_receipt_usecase()
        result = await usecase.extract_and_save(
            user_id=chat_id,
            image_bytes=image_bytes,
            context=context
        )
        msg_response = result.get("message") or result.get("error", "❌ Gagal memproses struk.")
        await self.notifier.send_message(chat_id, msg_response)

    async def execute(self, update: Update) -> None:
        logger.info(f"Update diterima: {update.model_dump()}")

        if not update.message:
            logger.warning("No message in update")
            return

        msg: Message = update.message
        chat_id = msg.chat.id
        text = (msg.text or "").strip()

        logger.info(f"Processing message from {chat_id}: '{text}'")

        # --- 1. User Management ---
        user = await self.user_repo.get(chat_id)

        if not user:
            logger.info(f"User baru: {chat_id}")
            user = TelegramUser(
                id=chat_id,
                first_name=msg.chat.first_name,
                username=getattr(msg.chat, "username", None),
                is_active=True
            )
            await self.user_repo.upsert(user)

        # --- 2. Active State Check ---
        try:
            ensure_active(user)
        except Exception as e:
            await self.notifier.send_message(chat_id, f"⛔ {str(e)}")
            return

        # --- 3. Command Handling (Legacy & System) ---
        if msg.photo:
            logger.info(f"Photo message received from {chat_id}")
            await self._handle_photo(msg, user, chat_id)
            return

        if text == "/start":
            await self.notifier.send_message(
                chat_id,
                f"Yo {user.first_name}! 🎉\n"
                "Dompetmu layak punya teman yang ngerti—dan yep, itu aku! 😏\n"
                "Ayo catat, pantau, dan rayakan tiap langkah kecilmu menuju finansial sehat! 🚀"
            )
            return

        # Command legacy (backward compatibility) - diprioritaskan sebelum intent detection
        if text == "/saldo":
            logger.info(f"Legacy command: /saldo for user {chat_id}")
            msg_response = await self.trans_service.get_balance_summary(chat_id)
            await self.notifier.send_message(chat_id, msg_response)
            return

        if text == "/riwayat":
            logger.info(f"Legacy command: /riwayat for user {chat_id}")
            msg_response = await self.trans_service.get_last_transactions(chat_id)
            await self.notifier.send_message(chat_id, msg_response)
            return

        # --- 4. Intent-Based Routing (Hanya jika IDLE) ---
        if user.current_state == "IDLE":
            intent = _detect_intent(text)
            logger.info(f"User {chat_id} | Detected Intent: [{intent}] | Text: '{text}'")

            if intent == "balance":
                logger.info(f"Routing to BALANCE handler for user {chat_id}")
                msg_response = await self.trans_service.get_balance_summary(chat_id)
                await self.notifier.send_message(chat_id, msg_response)
                return

            elif intent == "history":
                logger.info(f"Routing to HISTORY handler for user {chat_id}")
                msg_response = await self.trans_service.get_last_transactions(chat_id)
                await self.notifier.send_message(chat_id, msg_response)
                return

            elif intent == "debt":
                logger.info(f"Routing to DEBT handler for user {chat_id}")
                usecase = await resolve_manage_debt_usecase()
                result = await usecase.get_debt_summary(chat_id)
                msg_response = result.get("summary") or result.get("error", "Gagal mengambil data hutang/piutang")
                await self.notifier.send_message(chat_id, msg_response)
                return

            # Default: Transaction via LLM
            logger.info(f"Routing to LLM TRANSACTION handler for user {chat_id}")
            if not await self._check_ai_quota(user):
                return

            response_text = await self.trans_service.process_natural_language(chat_id, text)
            await self.notifier.send_message(chat_id, response_text)
            return

        # --- 5. Fallback: User tidak dalam state IDLE ---
        logger.info(f"User {chat_id} in state '{user.current_state}', forwarding to LLM")
        if not await self._check_ai_quota(user):
            return

        response_text = await self.trans_service.process_natural_language(chat_id, text)
        await self.notifier.send_message(chat_id, response_text)
