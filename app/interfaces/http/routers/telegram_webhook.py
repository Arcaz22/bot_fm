from fastapi import APIRouter, Depends
from app.presentation.schemas.telegram import Update, WebhookResponse
from app.core.di import get_telegram_update_queue
from app.infrastructure.telegram.queue import TelegramUpdateQueue
from app.application.services.telegram_service import TelegramWebhookService

router = APIRouter(tags=["telegram"])

@router.post("/webhook", response_model=WebhookResponse)
async def telegram_webhook(
    update: Update,
    update_queue: TelegramUpdateQueue = Depends(get_telegram_update_queue),
):
    queued = await update_queue.enqueue(update)
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
