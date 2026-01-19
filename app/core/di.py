from functools import lru_cache
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.base import get_db
from app.infrastructure.db.repositories.telegram import SqlTelegramUserRepo
from app.infrastructure.telegram.client import TelegramClient
from app.application.usecases.telegram import HandleTelegramUpdate

# =========================================================
# CLIENT DEPENDENCY (Notifier)
# =========================================================
# Menggunakan lru_cache agar object Client dibuat sekali saja (Singleton)
@lru_cache()
def get_telegram_client():
    return TelegramClient()

# =========================================================
# REPOSITORY DEPENDENCY (Database Access)
# =========================================================
# Fungsi ini butuh Session DB, jadi dia harus Async
async def get_user_repo(session: AsyncSession = Depends(get_db)):
    return SqlTelegramUserRepo(session)

# =========================================================
# USECASE DEPENDENCY (Main Logic)
# =========================================================
# Fungsi ini merakit UseCase dengan menyuntikkan Repo dan Client
async def get_handle_update(
    user_repo: SqlTelegramUserRepo = Depends(get_user_repo),
    telegram_client: TelegramClient = Depends(get_telegram_client)
):
    return HandleTelegramUpdate(
        user_repo=user_repo,
        notifier=telegram_client
    )
