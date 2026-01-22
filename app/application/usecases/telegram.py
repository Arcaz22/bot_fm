import logging
from app.application.services.transaction_service import TransactionService
from app.presentation.schemas.telegram import Update, Message
from app.domain.telegram.entities import TelegramUser
from app.domain.telegram.rules import ensure_active, reset_to_idle
from app.domain.telegram.ports import TelegramUserRepo, TelegramNotifier

logger = logging.getLogger(__name__)

def _detect_intent(text: str) -> str:
    text_lower = text.lower()

    balance_keywords = [
        "saldo", "balance", "duit", "uang", "total aset", "total asset",
        "punya berapa", "sisa berapa", "kekayaan", "dana"
    ]
    if any(keyword in text_lower for keyword in balance_keywords):
        if not any(trx_word in text_lower for trx_word in ["beli", "bayar", "transfer", "kirim", "dapat", "terima"]):
            return "balance"

    history_keywords = [
        "riwayat", "history", "transaksi terakhir", "transaksi sebelumnya",
        "histori", "pencatatan", "catatan transaksi", "5 terakhir"
    ]
    if any(keyword in text_lower for keyword in history_keywords):
        return "history"

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

    async def execute(self, update: Update) -> None:
        logger.info(f"Update diterima: {update.model_dump()}")
        if not update.message:
            return

        msg: Message = update.message
        chat_id = msg.chat.id
        text = (msg.text or "").strip()

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

        try:
            ensure_active(user)
        except Exception as e:
            await self.notifier.send_message(chat_id, f"⛔ {str(e)}")
            return

        if text == "/start":
            await self.notifier.send_message(
                chat_id,
                f"Yo {user.first_name}! 🎉\n"
                "Dompetmu layak punya teman yang ngerti—dan yep, itu aku! 😏\n"
                "Ayo catat, pantau, dan rayakan tiap langkah kecilmu menuju finansial sehat! 🚀"
            )
            return

        # ============================================================
        # HYBRID INTENT DETECTION
        # ============================================================
        # Command legacy (backward compatibility)
        if text == "/saldo":
            msg = await self.trans_service.get_balance_summary(chat_id)
            await self.notifier.send_message(chat_id, msg)
            return

        if text == "/riwayat":
            msg = await self.trans_service.get_last_transactions(chat_id)
            await self.notifier.send_message(chat_id, msg)
            return

        if user.current_state == "IDLE":
            intent = _detect_intent(text)

            if intent == "balance":
                logger.info(f"Intent detected: CHECK_BALANCE untuk user {chat_id}")
                msg = await self.trans_service.get_balance_summary(chat_id)
                await self.notifier.send_message(chat_id, msg)
                return

            elif intent == "history":
                logger.info(f"Intent detected: CHECK_HISTORY untuk user {chat_id}")
                msg = await self.trans_service.get_last_transactions(chat_id)
                await self.notifier.send_message(chat_id, msg)
                return

            logger.info(f"Intent detected: TRANSACTION untuk user {chat_id}, processing via LLM")
            response_text = await self.trans_service.process_natural_language(chat_id, text)

            await self.notifier.send_message(chat_id, response_text)
            return
