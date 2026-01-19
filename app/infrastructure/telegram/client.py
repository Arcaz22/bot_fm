import logging
import httpx
import time
from app.core.settings import settings

class TelegramClient:
    def __init__(self, bot_token: str | None = None):
        self.bot_token = bot_token or settings.TELEGRAM_TOKEN

        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self.logger = logging.getLogger(__name__)

    async def post(self, path: str, json: dict) -> dict:
        request_id = f"req_{int(time.time())}"
        self.logger.info(f"[{request_id}] Starting POST request to {path}")
        self.logger.debug(f"[{request_id}] Request payload: {json}")

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}{path}", json=json)

                try:
                    response_data = resp.json()
                except Exception:
                    response_data = {"raw": resp.text}

                duration = time.time() - start_time

                self.logger.info(
                    f"[{request_id}] Telegram API response received in {duration:.2f}s"
                    f" - Status: {resp.status_code}"
                )
                self.logger.debug(f"[{request_id}] Full response: {response_data}")
                return response_data

        except httpx.TimeoutException as e:
            duration = time.time() - start_time
            self.logger.error(
                f"[{request_id}] Timeout after {duration:.2f}s during POST {path}: {str(e)}"
            )
            return {"ok": False, "error": "Request timed out"}

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                f"[{request_id}] Error after {duration:.2f}s during POST {path}: {str(e)}"
            )
            return {"ok": False, "error": str(e)}

    async def send_message(self, chat_id: int, text: str,
                           parse_mode: str = None, reply_markup=None) -> bool:
        msg_id = f"msg_{int(time.time())}"
        self.logger.info(f"[{msg_id}] Preparing message for chat_id: {chat_id}")
        self.logger.debug(f"[{msg_id}] Message content: {text}")

        data = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup

        result = await self.post("/sendMessage", data)

        if not result or not result.get("ok"):
            self.logger.error(
                f"[{msg_id}] Failed to send message:"
                f" {result.get('error', 'Unknown error') if result else 'No response'}"
            )
            return False
        else:
            self.logger.info(
                f"[{msg_id}] Message delivered successfully:"
                f" message_id={result.get('result', {}).get('message_id')}"
            )
            return True
