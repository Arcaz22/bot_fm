from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.settings import settings
from app.infrastructure.telegram.client import TelegramClient
from app.interfaces.http.routers.telegram_webhook import _verify_webhook_secret


def test_webhook_secret_requires_matching_header():
    with patch.object(settings, "TELEGRAM_WEBHOOK_SECRET", "test-secret"):
        _verify_webhook_secret("test-secret")

        with pytest.raises(HTTPException) as exc_info:
            _verify_webhook_secret("wrong-secret")

    assert exc_info.value.status_code == 403


async def test_send_message_retries_plain_text_when_markdown_is_invalid():
    client = TelegramClient(bot_token="test-token")
    client.post = AsyncMock(
        side_effect=[
            {
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: can't parse entities",
            },
            {"ok": True, "result": {"message_id": 10}},
        ]
    )

    result = await client.send_message(123, "dynamic _text_", reply_markup={"x": 1})

    assert result is True
    assert client.post.await_count == 2
    first_payload = client.post.await_args_list[0].args[1]
    second_payload = client.post.await_args_list[1].args[1]
    assert first_payload["parse_mode"] == "Markdown"
    assert "parse_mode" not in second_payload
    assert second_payload["reply_markup"] == {"x": 1}
