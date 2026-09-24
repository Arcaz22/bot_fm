import httpx
from app.core.settings import settings

class TelegramWebhookService:
    @staticmethod
    async def set_webhook():
        url = getattr(settings, "WEBHOOK_URL", None)
        if not url:
            return {"error": "WEBHOOK_URL belum di-set di settings/env"}
        if not settings.TELEGRAM_WEBHOOK_SECRET:
            return {"error": "TELEGRAM_WEBHOOK_SECRET belum di-set di settings/env"}
        api_url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/setWebhook"
        payload = {
            "url": url,
            "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
            "allowed_updates": settings.TELEGRAM_ALLOWED_UPDATES,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(api_url, json=payload)
                return resp.json()
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"Gagal mengatur webhook: {exc}"}

    @staticmethod
    async def get_webhook_info():
        api_url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/getWebhookInfo"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(api_url)
                return resp.json()
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"Gagal mengambil info webhook: {exc}"}
