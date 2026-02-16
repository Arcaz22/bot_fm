import httpx
from app.core.settings import settings

class TelegramWebhookService:
    @staticmethod
    async def set_webhook():
        url = getattr(settings, "WEBHOOK_URL", None)
        if not url:
            return {"error": "WEBHOOK_URL belum di-set di settings/env"}
        api_url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/setWebhook"
        async with httpx.AsyncClient() as client:
            resp = await client.post(api_url, json={"url": url})
            return resp.json()

    @staticmethod
    async def get_webhook_info():
        api_url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/getWebhookInfo"
        async with httpx.AsyncClient() as client:
            resp = await client.get(api_url)
            return resp.json()
