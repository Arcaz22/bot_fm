import logging
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel

from app.application.usecases.debt import ManageDebt
from app.core.di import get_manage_debt_usecase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debt", tags=["debt"])


# Response Schemas
class DebtCreateResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None
    error: Optional[str] = None


class DebtSummaryResponse(BaseModel):
    success: bool
    summary: Optional[str] = None
    data: Optional[dict] = None
    error: Optional[str] = None


class DebtPayResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None
    error: Optional[str] = None


@router.post("/create", response_model=DebtCreateResponse)
async def create_debt(
    creditor_user_id: int = Form(..., description="User ID yang bayar duluan (punya piutang)"),
    debtor_user_id: int = Form(..., description="User ID yang ngutang (punya hutang)"),
    amount: float = Form(..., gt=0, description="Jumlah hutang"),
    description: str = Form(..., description="Deskripsi singkat (misal: 'Bayar makan bareng')"),
    notes: Optional[str] = Form(default=None, description="Catatan tambahan (optional)"),
    usecase: ManageDebt = Depends(get_manage_debt_usecase)
):
    """
    Create hutang-piutang record

    **Scenario:**
    - User A bayar makan untuk User B → A = creditor, B = debtor
    - User A upload receipt, sebagian untuk User B → A = creditor, B = debtor

    **Example:**
    ```
    creditor_user_id: 123456789 (User A - yang bayar)
    debtor_user_id: 987654321 (User B - yang ngutang)
    amount: 150000
    description: "Bayar makan di warung"
    ```
    """
    result = await usecase.create_debt(
        creditor_user_id=creditor_user_id,
        debtor_user_id=debtor_user_id,
        amount=amount,
        description=description,
        notes=notes
    )

    return DebtCreateResponse(
        success=result["success"],
        message=result.get("message"),
        data=result.get("data"),
        error=result.get("error")
    )


@router.get("/summary/{user_id}", response_model=DebtSummaryResponse)
async def get_debt_summary(
    user_id: int,
    usecase: ManageDebt = Depends(get_manage_debt_usecase)
):
    """
    Get ringkasan hutang dan piutang user

    Returns:
    - Total hutang (yang harus dibayar)
    - Total piutang (yang harus dibayar ke user)
    - List detail hutang
    - List detail piutang
    """
    result = await usecase.get_debt_summary(user_id)

    return DebtSummaryResponse(
        success=result["success"],
        summary=result.get("summary"),
        data=result.get("data"),
        error=result.get("error")
    )


@router.post("/pay", response_model=DebtPayResponse)
async def pay_debt(
    debt_id: int = Form(..., description="ID hutang yang mau dilunasi"),
    user_id: int = Form(..., description="User ID yang melakukan action"),
    transaction_id: Optional[int] = Form(default=None, description="Transaction ID jika ada pembayaran via transfer"),
    usecase: ManageDebt = Depends(get_manage_debt_usecase)
):
    """
    Mark hutang sebagai lunas

    **Who can mark:**
    - Creditor (yang punya piutang) - untuk confirm sudah dibayar
    - Debtor (yang hutang) - untuk inform sudah bayar

    **Example:**
    ```
    debt_id: 5
    user_id: 123456789
    transaction_id: 42 (optional - jika bayar via transfer dalam app)
    ```
    """
    result = await usecase.pay_debt(
        debt_id=debt_id,
        user_id=user_id,
        transaction_id=transaction_id
    )

    return DebtPayResponse(
        success=result["success"],
        message=result.get("message"),
        data=result.get("data"),
        error=result.get("error")
    )
