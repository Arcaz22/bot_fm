import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.di import (
    get_redis_client,
    get_telegram_update_queue,
    process_telegram_update_from_queue,
)
from app.core.settings import settings
from app.infrastructure.telegram.queue import close_redis
from app.infrastructure.llm.client import shutdown_langfuse_client
from app.interfaces.http.routers.telegram_webhook import router as telegram_router
from app.interfaces.http.routers.receipt import router as receipt_router
from app.interfaces.http.routers.debt import router as debt_router
from app.interfaces.http.routers.dashboard import router as dashboard_router
from app.interfaces.http.routers.subscription import router as subscription_router
from app.interfaces.http.routers.membership import router as membership_router
from app.interfaces.http.routers.langfuse import router as langfuse_router
from app.interfaces.http.routers.payment import router as payment_router
from app.interfaces.http.routers.legal import router as legal_router

from app.core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    update_queue = get_telegram_update_queue()
    workers = [
        asyncio.create_task(
            update_queue.run_worker(process_telegram_update_from_queue, stop_event)
        )
        for _ in range(settings.TELEGRAM_QUEUE_WORKERS)
    ]
    logger.info("Started %s Telegram Redis queue worker(s)", len(workers))

    try:
        yield
    finally:
        stop_event.set()
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker
        await close_redis(get_redis_client())
        shutdown_langfuse_client()
        logger.info("Stopped Telegram Redis queue worker(s)")

app = FastAPI(
    title="FINANCIAL MANAGEMENT API",
    description="FM API DOCUMENTATION",
    version="0.0.2",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telegram_router)
app.include_router(receipt_router)
app.include_router(debt_router)
app.include_router(dashboard_router)
app.include_router(subscription_router)
app.include_router(membership_router)
app.include_router(langfuse_router)
app.include_router(payment_router)
app.include_router(legal_router)

@app.get("/")
async def root():
    return {"message": "Welcome to FINANCIAL MANAGEMENT API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "finance-bot"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.APP_PORT)
