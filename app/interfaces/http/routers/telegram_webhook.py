import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from app.presentation.schemas.telegram import Update, WebhookResponse
from app.core.di import get_telegram_update_queue
from app.core.di import get_telegram_client
from app.core.settings import settings
from app.infrastructure.telegram.client import TelegramClient
from app.infrastructure.telegram.queue import TelegramUpdateQueue
from app.application.services.telegram_service import TelegramWebhookService

router = APIRouter(tags=["telegram"])
logger = logging.getLogger(__name__)


def _verify_webhook_secret(secret_header: str | None) -> None:
    configured_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram webhook secret belum dikonfigurasi",
        )

    if not secret_header or not hmac.compare_digest(secret_header, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram webhook secret tidak valid",
        )

@router.post("/webhook", response_model=WebhookResponse)
async def telegram_webhook(
    update: Update,
    update_queue: TelegramUpdateQueue = Depends(get_telegram_update_queue),
    telegram_client: TelegramClient = Depends(get_telegram_client),
    telegram_secret: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
):
    _verify_webhook_secret(telegram_secret)
    queued = await update_queue.enqueue(update)
    if queued:
        chat_id = update_queue.extract_chat_id(update)
        if chat_id is not None:
            try:
                sent = await telegram_client.send_message(
                    chat_id,
                    "⏳ Pesan Anda sedang diproses...",
                    parse_mode="",
                )
                if not sent:
                    logger.warning(
                        "Failed to send Telegram processing notification for chat_id=%s",
                        chat_id,
                    )
            except Exception:
                logger.exception(
                    "Error while sending Telegram processing notification for chat_id=%s",
                    chat_id,
                )
    message = "Update queued" if queued else "Duplicate or unsupported update ignored"
    return WebhookResponse(status="success", message=message)

@router.get("/webhook/telegram/info")
async def get_telegram_webhook_info():
    """
    Endpoint untuk cek info webhook Telegram via service.
    """
    return await TelegramWebhookService.get_webhook_info()

@router.get("/webhook/telegram/set")
async def set_telegram_webhook_get():
    """
    Endpoint GET untuk set webhook Telegram via service.
    """
    return await TelegramWebhookService.set_webhook()
