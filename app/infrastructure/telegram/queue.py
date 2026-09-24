import asyncio
import json
import logging
from contextlib import suppress
from typing import Awaitable, Callable

from redis.asyncio import Redis

from app.core.settings import settings
from app.domain.telegram.ports import TelegramNotifier
from app.presentation.schemas.telegram import Update

logger = logging.getLogger(__name__)


ENQUEUE_SCRIPT = """
local dedupe_key = KEYS[1]
local user_queue_key = KEYS[2]
local active_users_key = KEYS[3]
local ready_queue_key = KEYS[4]
local user_id = ARGV[1]
local payload = ARGV[2]
local ttl = tonumber(ARGV[3])

if redis.call("SET", dedupe_key, "1", "NX", "EX", ttl) == false then
    return 0
end

redis.call("RPUSH", user_queue_key, payload)
if redis.call("SADD", active_users_key, user_id) == 1 then
    redis.call("RPUSH", ready_queue_key, user_id)
end

return 1
"""

FINALIZE_USER_SCRIPT = """
local user_queue_key = KEYS[1]
local active_users_key = KEYS[2]
local ready_queue_key = KEYS[3]
local user_id = ARGV[1]

if redis.call("LLEN", user_queue_key) == 0 then
    redis.call("SREM", active_users_key, user_id)
else
    redis.call("RPUSH", ready_queue_key, user_id)
end

return 1
"""


class TelegramUpdateQueue:
    def __init__(self, redis: Redis, notifier: TelegramNotifier):
        self.redis = redis
        self.notifier = notifier
        self.ready_queue_key = "telegram:updates:ready"
        self.active_users_key = "telegram:updates:active_users"
        self.dedupe_ttl_seconds = settings.TELEGRAM_UPDATE_DEDUPE_TTL_SECONDS
        self.lock_ttl_seconds = settings.TELEGRAM_USER_QUEUE_LOCK_TTL_SECONDS
        self.max_retries = settings.TELEGRAM_QUEUE_MAX_RETRIES
        self.dead_letter_key = "telegram:updates:dead_letter"

    def _user_queue_key(self, chat_id: int) -> str:
        return f"telegram:updates:user:{chat_id}"

    def _dedupe_key(self, update_id: int) -> str:
        return f"telegram:updates:dedupe:{update_id}"

    def _lock_key(self, chat_id: int) -> str:
        return f"telegram:updates:lock:{chat_id}"

    def _attempt_key(self, update_id: int) -> str:
        return f"telegram:updates:attempts:{update_id}"

    async def enqueue(self, update: Update) -> bool:
        chat_id = self.extract_chat_id(update)
        if chat_id is None:
            logger.warning("Telegram update ignored because chat_id is missing: %s", update.model_dump())
            return False

        payload = update.model_dump_json()
        inserted = await self.redis.eval(
            ENQUEUE_SCRIPT,
            4,
            self._dedupe_key(update.update_id),
            self._user_queue_key(chat_id),
            self.active_users_key,
            self.ready_queue_key,
            str(chat_id),
            payload,
            str(self.dedupe_ttl_seconds),
        )
        return bool(inserted)

    async def run_worker(
        self,
        handler: Callable[[Update], Awaitable[None]],
        stop_event: asyncio.Event,
    ) -> None:
        while not stop_event.is_set():
            try:
                item = await self.redis.blpop(self.ready_queue_key, timeout=1)
                if not item:
                    continue

                _, raw_user_id = item
                chat_id = int(raw_user_id)
                await self._process_user_queue(chat_id, handler)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram update queue worker failed")

    async def _process_user_queue(
        self,
        chat_id: int,
        handler: Callable[[Update], Awaitable[None]],
    ) -> None:
        lock_key = self._lock_key(chat_id)
        locked = await self.redis.set(lock_key, "1", nx=True, ex=self.lock_ttl_seconds)
        if not locked:
            return

        try:
            queue_key = self._user_queue_key(chat_id)
            while True:
                raw_payload = await self.redis.lpop(queue_key)
                if raw_payload is None:
                    break

                try:
                    update = Update.model_validate_json(raw_payload)
                    await handler(update)
                    await self.redis.delete(self._attempt_key(update.update_id))
                except Exception:
                    update_id = None
                    try:
                        update_id = Update.model_validate_json(raw_payload).update_id
                    except Exception:
                        pass

                    attempt = 1
                    if update_id is not None:
                        attempt = int(await self.redis.incr(self._attempt_key(update_id)))
                        await self.redis.expire(
                            self._attempt_key(update_id),
                            self.dedupe_ttl_seconds,
                        )

                    if attempt <= self.max_retries:
                        await self.redis.rpush(queue_key, raw_payload)
                        logger.exception(
                            "Failed to process Telegram update for chat_id=%s; retry %s/%s",
                            chat_id,
                            attempt,
                            self.max_retries,
                        )
                        await asyncio.sleep(min(2 ** (attempt - 1), 30))
                    else:
                        await self.redis.rpush(self.dead_letter_key, raw_payload)
                        await self._notify_processing_failed(chat_id)
                        logger.exception(
                            "Telegram update moved to dead-letter queue: chat_id=%s update_id=%s",
                            chat_id,
                            update_id,
                        )
        finally:
            await self.redis.delete(lock_key)
            await self.redis.eval(
                FINALIZE_USER_SCRIPT,
                3,
                self._user_queue_key(chat_id),
                self.active_users_key,
                self.ready_queue_key,
                str(chat_id),
            )

    @staticmethod
    def extract_chat_id(update: Update) -> int | None:
        if update.message:
            return update.message.chat.id
        if update.edited_message:
            return update.edited_message.chat.id
        if update.callback_query and update.callback_query.message:
            return update.callback_query.message.chat.id
        return None

    async def _notify_processing_failed(self, chat_id: int) -> None:
        """Notify the user after the update is permanently dead-lettered.

        Notification delivery is best effort: a Telegram API failure must not
        cause the worker to retry an update that has already reached its retry
        limit.
        """
        try:
            sent = await self.notifier.send_message(
                chat_id,
                "❌ Maaf, pesan Anda gagal diproses setelah beberapa percobaan. "
                "Silakan coba lagi nanti.",
                parse_mode="",
            )
            if not sent:
                logger.warning(
                    "Failed to send permanent Telegram processing failure notification "
                    "for chat_id=%s",
                    chat_id,
                )
        except Exception:
            logger.exception(
                "Error while sending permanent Telegram processing failure notification "
                "for chat_id=%s",
                chat_id,
            )


async def close_redis(redis: Redis) -> None:
    with suppress(Exception):
        await redis.aclose()
