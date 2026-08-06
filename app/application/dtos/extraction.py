from pydantic import BaseModel, Field, field_validator
from typing import Any, Literal, Optional, List


def _parse_receipt_money(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    raw = value.strip()
    if not raw:
        return value

    cleaned = raw.replace("Rp", "").replace("rp", "").replace("IDR", "").strip()
    cleaned = cleaned.replace(" ", "")

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            cleaned = "".join(parts)
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            cleaned = "".join(parts)
        else:
            cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return value


class ExtractedTransaction(BaseModel):
    amount: float
    category: str
    wallet_name: str = Field(default="BCA")
    target_wallet_name: Optional[str] = None
    description: str
    transaction_type: Literal["EXPENSE", "INCOME", "TRANSFER"] = "EXPENSE"

    debt_action: Literal["NONE", "BORROW", "LEND", "PAY"] = "NONE"
    counterparty_name: Optional[str] = None

    @field_validator("category", mode="before")
    @classmethod
    def default_category(cls, value):
        return value or "Other"

    @field_validator("wallet_name", mode="before")
    @classmethod
    def default_wallet_name(cls, value):
        return value or "BCA"

    @field_validator("description", mode="before")
    @classmethod
    def default_description(cls, value):
        return value or ""

    @field_validator("transaction_type", mode="before")
    @classmethod
    def default_transaction_type(cls, value):
        return value or "EXPENSE"

    @field_validator("debt_action", mode="before")
    @classmethod
    def default_debt_action(cls, value):
        return value or "NONE"


class ReceiptItem(BaseModel):
    name: str
    quantity: int = 1
    price: float
    category: str = "Uncategorized"

    @field_validator("price", mode="before")
    @classmethod
    def parse_price(cls, value):
        return _parse_receipt_money(value)


class ExtractedReceipt(BaseModel):
    store_name: Optional[str] = None
    items: List[ReceiptItem] = []
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: float
    transaction_date: Optional[str] = None

    @field_validator("subtotal", "tax", "total", mode="before")
    @classmethod
    def parse_money(cls, value):
        return _parse_receipt_money(value)


class ReceiptContext(BaseModel):
    wallet_name: Optional[str] = None
    default_category: Optional[str] = None
    notes: Optional[str] = None
    selected_items: Optional[List[int]] = None
    is_shared: bool = False
