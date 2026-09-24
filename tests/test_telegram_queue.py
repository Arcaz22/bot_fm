from unittest.mock import AsyncMock

from app.infrastructure.telegram.queue import TelegramUpdateQueue
from app.presentation.schemas.telegram import Chat, Message, Update


class FakeRedis:
    def __init__(self, payload: str):
        self.queues = {"telegram:updates:user:123": [payload]}
        self.attempts: dict[str, int] = {}
        self.dead_letter: list[str] = []

    async def set(self, *args, **kwargs):
        return True

    async def lpop(self, key):
        values = self.queues.setdefault(key, [])
        return values.pop(0) if values else None

    async def rpush(self, key, value):
        if key == "telegram:updates:dead_letter":
            self.dead_letter.append(value)
        else:
            self.queues.setdefault(key, []).append(value)

    async def incr(self, key):
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return self.attempts[key]

    async def expire(self, *args):
        return True

    async def delete(self, *args):
        return True

    async def eval(self, *args):
        return 1


def _update_payload() -> str:
    return Update(
        update_id=42,
        message=Message(
            message_id=1,
            chat=Chat(id=123),
            text="halo",
        ),
    ).model_dump_json()


async def test_permanent_failure_notifies_user_once(monkeypatch):
    notifier = AsyncMock()
    notifier.send_message.return_value = True
    redis = FakeRedis(_update_payload())
    queue = TelegramUpdateQueue(redis, notifier)
    queue.max_retries = 1
    handler = AsyncMock(side_effect=RuntimeError("handler failed"))
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    await queue._process_user_queue(123, handler)

    assert handler.await_count == 2
    assert len(redis.dead_letter) == 1
    notifier.send_message.assert_awaited_once_with(
        123,
        "❌ Maaf, pesan Anda gagal diproses setelah beberapa percobaan. "
        "Silakan coba lagi nanti.",
        parse_mode="",
    )


async def test_notification_failure_does_not_escape_worker(monkeypatch):
    notifier = AsyncMock()
    notifier.send_message.side_effect = RuntimeError("telegram unavailable")
    redis = FakeRedis(_update_payload())
    queue = TelegramUpdateQueue(redis, notifier)
    queue.max_retries = 0

    await queue._process_user_queue(123, AsyncMock(side_effect=RuntimeError("handler failed")))

    assert len(redis.dead_letter) == 1
    notifier.send_message.assert_awaited_once()
