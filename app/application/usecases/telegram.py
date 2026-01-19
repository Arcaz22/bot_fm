import logging
from app.presentation.schemas.telegram import Update, Message
from app.domain.telegram.entities import TelegramUser
from app.domain.telegram.rules import ensure_active, reset_to_idle
from app.domain.telegram.ports import TelegramUserRepo, TelegramNotifier

logger = logging.getLogger(__name__)

class HandleTelegramUpdate:
    def __init__(
        self,
        user_repo: TelegramUserRepo,
        notifier: TelegramNotifier,
    ):
        self.user_repo = user_repo
        self.notifier = notifier

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
                first_name=msg.chat.first_name or "Unknown",
                username=getattr(msg.chat, "username", None),
                is_active=True
            )

            await self.user_repo.upsert(user)

        ensure_active(user)

        if text == "/start":
            await self.notifier.send_message(
                chat_id,
                f"Yo {user.first_name}! 🎉\n"
                "Dompetmu layak punya teman yang ngerti—dan yep, itu aku! 😏\n"
                "Ayo catat, pantau, dan rayakan tiap langkah kecilmu menuju finansial sehat! 🚀"
            )
            return

        if user.current_state == "IDLE":
            try:
                amount = float(text)
                await self.notifier.send_message(chat_id, f"✅ Draft: {amount:,.0f}")
            except ValueError:
                await self.notifier.send_message(chat_id, "Saya belum mengerti text. Coba kirim angka.")
            return
