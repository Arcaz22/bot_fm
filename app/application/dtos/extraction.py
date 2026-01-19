from pydantic import BaseModel, Field
from typing import Literal, Optional

class ExtractedTransaction(BaseModel):
    amount: float
    category: str
    wallet_name: str = Field(default="BCA")
    target_wallet_name: Optional[str] = None
    description: str
    transaction_type: Literal["EXPENSE", "INCOME", "TRANSFER"] = "EXPENSE"
