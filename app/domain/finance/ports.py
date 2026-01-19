from typing import Protocol, Optional
from datetime import date
from app.infrastructure.db.models import MstWallet, MstCategory, TrsTransaction

class FinanceRepoPort(Protocol):
    async def get_wallet_by_name(self, user_id: int, name: str) -> Optional[MstWallet]: ...
    async def create_wallet(self, user_id: int, name: str, initial_balance: float = 0) -> MstWallet: ...
    async def get_wallet_balance(self, wallet_id: int) -> float: ...

    async def get_category_by_name(self, user_id: int, name: str, type: str) -> Optional[MstCategory]: ...
    async def create_category(self, user_id: int, name: str, type: str) -> MstCategory: ...

    async def create_transaction(
        self,
        user_id: int,
        wallet_id: int,
        amount: float,
        type: str,
        category_id: Optional[int] = None,
        description: str = None,
        trx_date: date = None,
        embedding_data: list[float] = None
    ) -> TrsTransaction: ...
