from dataclasses import dataclass
from datetime import date
from typing import Optional, Literal

TransactionType = Literal["income", "expense", "transfer"]

@dataclass
class Wallet:
    id: int
    name: str
    initial_balance: float
    current_balance: Optional[float] = None

@dataclass
class Transaction:
    id: int
    amount: float
    type: TransactionType
    description: str
    date: date
    wallet_name: str
    category_name: Optional[str] = None
