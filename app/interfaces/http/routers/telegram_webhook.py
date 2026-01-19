from fastapi import APIRouter, BackgroundTasks, Depends
from app.presentation.schemas.telegram import Update, WebhookResponse
from app.core.di import get_handle_update

router = APIRouter(prefix="/telegram", tags=["telegram"])

@router.post("/webhook", response_model=WebhookResponse)
async def telegram_webhook(update: Update, background_tasks: BackgroundTasks,
                           uc = Depends(get_handle_update)):
    background_tasks.add_task(uc.execute, update)
    return WebhookResponse(status="success", message="Update processed")
