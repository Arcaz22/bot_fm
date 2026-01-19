from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_
from app.infrastructure.db.models import MstWallet, MstCategory, TrsTransaction, SysTelegramUser
from typing import List, Optional
from datetime import date

class FinanceRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    # Wallet
    async def get_wallet_by_name(self, user_id: int, name: str) -> Optional[MstWallet]:
        stmt = select(MstWallet).where(
            MstWallet.owner_telegram_user_id == user_id,
            MstWallet.name.ilike(name),
            MstWallet.is_active == True
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_user_wallets(self, user_id: int) -> List[MstWallet]:
        stmt = select(MstWallet).where(
            MstWallet.owner_telegram_user_id == user_id,
            MstWallet.is_active == True
        ).order_by(MstWallet.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_wallet(self, user_id: int, name: str, initial_balance: float = 0) -> MstWallet:
        wallet = MstWallet(
            owner_telegram_user_id=user_id,
            name=name,
            initial_balance=initial_balance
        )
        self.session.add(wallet)
        await self.session.commit()
        await self.session.refresh(wallet)
        return wallet

   # Category
    async def get_category_by_name(self, user_id: int, name: str, type: str) -> Optional[MstCategory]:
        stmt = select(MstCategory).where(
            MstCategory.owner_telegram_user_id == user_id,
            MstCategory.name.ilike(name),
            MstCategory.type == type,
            MstCategory.is_active == True
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_category(self, user_id: int, name: str, type: str) -> MstCategory:
        category = MstCategory(
            owner_telegram_user_id=user_id,
            name=name,
            type=type
        )
        self.session.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    # Transaction
    async def create_transaction(
        self,
        user_id: int,
        wallet_id: int,
        amount: float,
        type: str,  # 'income', 'expense', 'transfer'
        category_id: Optional[int] = None,
        target_wallet_id: Optional[int] = None,
        description: str = None,
        trx_date: date = None,
        embedding_data: list[float] = None
    ) -> TrsTransaction:

        if not trx_date:
            from datetime import date
            trx_date = date.today()

        trx = TrsTransaction(
            owner_telegram_user_id=user_id,
            wallet_id=wallet_id,
            category_id=category_id,
            target_wallet_id=target_wallet_id,
            type=type,
            amount=amount,
            description=description,
            trx_date=trx_date,
            embedding_data=embedding_data
        )
        self.session.add(trx)
        await self.session.commit()
        await self.session.refresh(trx)
        return trx

    async def get_recent_transactions(self, user_id: int, limit: int = 5) -> List[TrsTransaction]:
        from sqlalchemy.orm import joinedload

        stmt = select(TrsTransaction).options(
            joinedload(TrsTransaction.wallet),
            joinedload(TrsTransaction.category),
            joinedload(TrsTransaction.target_wallet)
        ).where(
            TrsTransaction.owner_telegram_user_id == user_id
        ).order_by(desc(TrsTransaction.created_at)).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # Reporting
    async def get_wallet_balance(self, wallet_id: int) -> float:
        """
        Hitung saldo real-time berdasarkan history transaksi
        Rumus: Initial + Income - Expense - Transfer Keluar + Transfer Masuk
        """
        # Ambil Initial Balance dulu
        w_stmt = select(MstWallet.initial_balance).where(MstWallet.id == wallet_id)
        w_res = await self.session.execute(w_stmt)
        initial = w_res.scalar() or 0

        # Hitung Income
        inc_stmt = select(func.sum(TrsTransaction.amount)).where(
            TrsTransaction.wallet_id == wallet_id,
            TrsTransaction.type == 'income'
        )
        inc = (await self.session.execute(inc_stmt)).scalar() or 0

        # Hitung Expense
        exp_stmt = select(func.sum(TrsTransaction.amount)).where(
            TrsTransaction.wallet_id == wallet_id,
            TrsTransaction.type == 'expense'
        )
        exp = (await self.session.execute(exp_stmt)).scalar() or 0

        # Hitung Transfer Keluar (Dari wallet ini ke orang lain)
        trf_out_stmt = select(func.sum(TrsTransaction.amount)).where(
            TrsTransaction.wallet_id == wallet_id,
            TrsTransaction.type == 'transfer'
        )
        trf_out = (await self.session.execute(trf_out_stmt)).scalar() or 0

        # Hitung Transfer Masuk (Dari orang lain ke wallet ini)
        trf_in_stmt = select(func.sum(TrsTransaction.amount)).where(
            TrsTransaction.target_wallet_id == wallet_id,
            TrsTransaction.type == 'transfer'
        )
        trf_in = (await self.session.execute(trf_in_stmt)).scalar() or 0

        return float(initial) + float(inc) - float(exp) - float(trf_out) + float(trf_in)
