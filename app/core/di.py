from functools import lru_cache
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.base import get_db

# --- REPOSITORIES ---
from app.infrastructure.db.repositories.telegram import SqlTelegramUserRepo
from app.infrastructure.db.repositories.finance import FinanceRepo  # <-- Repository Baru

# --- CLIENTS & INFRA ---
from app.infrastructure.telegram.client import TelegramClient
from app.infrastructure.llm.client import GeminiLLM  # <-- LLM Baru

# --- SERVICES & USECASES ---
from app.application.services.transaction_service import TransactionService # <-- Service Baru
from app.application.usecases.telegram import HandleTelegramUpdate

# =========================================================
# 1. INFRASTRUCTURE & CLIENTS (Singleton)
# =========================================================
@lru_cache()
def get_telegram_client():
    return TelegramClient()

@lru_cache()
def get_llm_client():
    # Inisialisasi Gemini LLM (Singleton)
    return GeminiLLM()

# =========================================================
# 2. REPOSITORIES (Scoped per Request)
# =========================================================
async def get_user_repo(session: AsyncSession = Depends(get_db)):
    return SqlTelegramUserRepo(session)

async def get_finance_repo(session: AsyncSession = Depends(get_db)):
    # Inject session ke FinanceRepo
    return FinanceRepo(session)

# =========================================================
# 3. APPLICATION SERVICES (Logic Layer)
# =========================================================
async def get_transaction_service(
    llm: GeminiLLM = Depends(get_llm_client),
    finance_repo: FinanceRepo = Depends(get_finance_repo)
):
    # Rakit Service: Butuh Otak AI (LLM) & Otot Database (FinanceRepo)
    return TransactionService(llm=llm, repo=finance_repo)

# =========================================================
# 4. USECASES (Main Entry Point)
# =========================================================
async def get_handle_update(
    user_repo: SqlTelegramUserRepo = Depends(get_user_repo),
    telegram_client: TelegramClient = Depends(get_telegram_client),
    trans_service: TransactionService = Depends(get_transaction_service) # <-- Inject Service Transaksi
):
    return HandleTelegramUpdate(
        user_repo=user_repo,
        notifier=telegram_client,
        trans_service=trans_service  # Masukkan service ke UseCase Telegram
    )
