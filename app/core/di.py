# Helper async untuk resolve ManageDebt usecase di luar FastAPI (misal, handler Telegram)
from app.infrastructure.db.base import async_session
from app.infrastructure.db.repositories.finance import FinanceRepo
from app.application.services.debt_service import DebtService
from app.application.usecases.debt import ManageDebt

async def resolve_manage_debt_usecase():
    async with async_session() as session:
        repo = FinanceRepo(session)
        debt_service = DebtService(repo=repo)
        return ManageDebt(debt_service=debt_service)

async def resolve_process_receipt_usecase():
    from app.application.services.receipt_service import ReceiptService
    from app.application.usecases.receipt import ProcessReceiptImage
    from app.infrastructure.llm.client import GeminiLLM
    async with async_session() as session:
        repo = FinanceRepo(session)
        llm = GeminiLLM()
        receipt_service = ReceiptService(llm=llm, repo=repo)
        return ProcessReceiptImage(receipt_service=receipt_service)
from functools import lru_cache
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.base import get_db

# --- REPOSITORIES ---
from app.infrastructure.db.repositories.telegram import SqlTelegramUserRepo
from app.infrastructure.db.repositories.finance import FinanceRepo

# --- CLIENTS & INFRA ---
from app.infrastructure.telegram.client import TelegramClient
from app.infrastructure.llm.client import GeminiLLM

# --- SERVICES & USECASES ---
from app.application.services.transaction_service import TransactionService
from app.application.services.receipt_service import ReceiptService
from app.application.services.debt_service import DebtService
from app.application.usecases.telegram import HandleTelegramUpdate
from app.application.usecases.receipt import ProcessReceiptImage
from app.application.usecases.debt import ManageDebt

# =========================================================
# 1. INFRASTRUCTURE & CLIENTS (Singleton)
# =========================================================
@lru_cache()
def get_telegram_client():
    return TelegramClient()

@lru_cache()
def get_llm_client():
    return GeminiLLM()

# =========================================================
# 2. REPOSITORIES (Scoped per Request)
# =========================================================
async def get_user_repo(session: AsyncSession = Depends(get_db)):
    return SqlTelegramUserRepo(session)

async def get_finance_repo(session: AsyncSession = Depends(get_db)):
    return FinanceRepo(session)

# =========================================================
# 3. APPLICATION SERVICES (Logic Layer)
# =========================================================
async def get_transaction_service(
    llm: GeminiLLM = Depends(get_llm_client),
    finance_repo: FinanceRepo = Depends(get_finance_repo)
):
    return TransactionService(llm=llm, repo=finance_repo)

async def get_receipt_service(
    llm: GeminiLLM = Depends(get_llm_client),
    finance_repo: FinanceRepo = Depends(get_finance_repo)
):
    return ReceiptService(llm=llm, repo=finance_repo)

async def get_debt_service(
    finance_repo: FinanceRepo = Depends(get_finance_repo)
):
    return DebtService(repo=finance_repo)

# =========================================================
# 4. USECASES (Main Entry Point)
# =========================================================
async def get_handle_update(
    user_repo: SqlTelegramUserRepo = Depends(get_user_repo),
    telegram_client: TelegramClient = Depends(get_telegram_client),
    trans_service: TransactionService = Depends(get_transaction_service)
):
    return HandleTelegramUpdate(
        user_repo=user_repo,
        notifier=telegram_client,
        trans_service=trans_service
    )

async def get_process_receipt_usecase(
    receipt_service: ReceiptService = Depends(get_receipt_service)
):
    return ProcessReceiptImage(receipt_service=receipt_service)

async def get_manage_debt_usecase(
    debt_service: DebtService = Depends(get_debt_service)
):
    return ManageDebt(debt_service=debt_service)
