from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.interfaces.http.routers.telegram_webhook import router as telegram_router
from app.interfaces.http.routers.receipt import router as receipt_router
from app.interfaces.http.routers.debt import router as debt_router

from app.core.logging import setup_logging

setup_logging()

app = FastAPI(
    title="FINANCIAL MANAGEMENT API",
    description="FM API DOCUMENTATION",
    version="0.0.2",
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
app.include_router(receipt_router)

@app.get("/")
async def root():
    return {"message": "Welcome to FINANCIAL MANAGEMENT API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
