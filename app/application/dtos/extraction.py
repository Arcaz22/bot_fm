from pydantic import BaseModel, Field
from typing import Literal, Optional, List


class ExtractedTransaction(BaseModel):
    amount: float
    category: str
    wallet_name: str = Field(default="BCA")
    target_wallet_name: Optional[str] = None
    description: str
    transaction_type: Literal["EXPENSE", "INCOME", "TRANSFER"] = "EXPENSE"

    debt_action: Literal["NONE", "BORROW", "LEND", "PAY"] = "NONE"
    counterparty_name: Optional[str] = None


class ReceiptItem(BaseModel):
    """Item tunggal dari nota"""
    name: str
    quantity: int = 1
    price: float
    category: str = "Uncategorized"


class ExtractedReceipt(BaseModel):
    """Hasil ekstraksi dari foto nota"""
    store_name: Optional[str] = None
    items: List[ReceiptItem] = []
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: float
    transaction_date: Optional[str] = None


class ReceiptContext(BaseModel):
    """Context yang diberikan user sebelum upload foto"""
    wallet_name: str = "BCA"
    default_category: Optional[str] = None
    notes: Optional[str] = None
    selected_items: Optional[List[int]] = None
    is_shared: bool = False
