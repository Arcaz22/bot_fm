from fastapi import Query
from fastapi.responses import JSONResponse

from fastapi import APIRouter, BackgroundTasks, Depends
from app.presentation.schemas.telegram import Update, WebhookResponse
from app.core.di import get_handle_update
from app.application.services.telegram_service import TelegramWebhookService

router = APIRouter(tags=["telegram"])

@router.post("/webhook", response_model=WebhookResponse)
async def telegram_webhook(update: Update, background_tasks: BackgroundTasks,
                           uc = Depends(get_handle_update)):
    background_tasks.add_task(uc.execute, update)
    return WebhookResponse(status="success", message="Update processed")

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
