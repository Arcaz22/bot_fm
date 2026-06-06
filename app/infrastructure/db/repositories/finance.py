from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_
from sqlalchemy.orm import joinedload
from app.infrastructure.db.models import MstWallet, MstCategory, MstCounterparty, TrsTransaction, TrsDebt, SysTelegramUser
from typing import List, Optional
from datetime import date, datetime

class FinanceRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

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

    async def find_user_by_name_or_username(self, query: str) -> Optional[SysTelegramUser]:
        stmt = select(SysTelegramUser).where(
            or_(
                SysTelegramUser.first_name.ilike(query),
                SysTelegramUser.username.ilike(query)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_counterparty_by_name(self, user_id: int, name: str) -> Optional[MstCounterparty]:
        stmt = select(MstCounterparty).where(
            MstCounterparty.owner_telegram_user_id == user_id,
            MstCounterparty.display_name.ilike(name.strip())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_or_create_counterparty(self, user_id: int, name: str) -> MstCounterparty:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Nama counterparty wajib diisi")

        counterparty = await self.get_counterparty_by_name(user_id, clean_name)
        if counterparty:
            return counterparty

        counterparty = MstCounterparty(
            owner_telegram_user_id=user_id,
            display_name=clean_name
        )
        self.session.add(counterparty)
        await self.session.commit()
        await self.session.refresh(counterparty)
        return counterparty

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

    async def create_transaction(
        self,
        user_id: int,
        wallet_id: int,
        amount: float,
        type: str,
        category_id: Optional[int] = None,
        target_wallet_id: Optional[int] = None,
        description: str = None,
        trx_date: date = None,
    ) -> TrsTransaction:

        if not trx_date:
            trx_date = date.today()

        trx = TrsTransaction(
            owner_telegram_user_id=user_id,
            wallet_id=wallet_id,
            category_id=category_id,
            target_wallet_id=target_wallet_id,
            type=type,
            amount=amount,
            description=description,
            trx_date=trx_date
        )
        self.session.add(trx)
        await self.session.commit()
        await self.session.refresh(trx)
        return trx

    async def get_recent_transactions(self, user_id: int, limit: int = 5) -> List[TrsTransaction]:
        stmt = select(TrsTransaction).options(
            joinedload(TrsTransaction.wallet),
            joinedload(TrsTransaction.category),
            joinedload(TrsTransaction.target_wallet)
        ).where(
            TrsTransaction.owner_telegram_user_id == user_id
        ).order_by(desc(TrsTransaction.created_at)).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_wallet_balance(self, wallet_id: int, user_id: int) -> float:

        w_stmt = select(MstWallet.initial_balance).where(
            MstWallet.id == wallet_id,
            MstWallet.owner_telegram_user_id == user_id
        )
        w_res = await self.session.execute(w_stmt)
        initial = w_res.scalar()

        if initial is None:
            raise ValueError(f"Wallet {wallet_id} tidak ditemukan atau bukan milik user {user_id}")

        inc_stmt = select(func.sum(TrsTransaction.amount)).where(
            TrsTransaction.wallet_id == wallet_id,
            TrsTransaction.owner_telegram_user_id == user_id,
            TrsTransaction.type == 'income'
        )
        inc = (await self.session.execute(inc_stmt)).scalar() or 0

        exp_stmt = select(func.sum(TrsTransaction.amount)).where(
            TrsTransaction.wallet_id == wallet_id,
            TrsTransaction.owner_telegram_user_id == user_id,
            TrsTransaction.type == 'expense'
        )
        exp = (await self.session.execute(exp_stmt)).scalar() or 0

        trf_out_stmt = select(func.sum(TrsTransaction.amount)).where(
            TrsTransaction.wallet_id == wallet_id,
            TrsTransaction.owner_telegram_user_id == user_id,
            TrsTransaction.type == 'transfer'
        )
        trf_out = (await self.session.execute(trf_out_stmt)).scalar() or 0

        trf_in_stmt = select(func.sum(TrsTransaction.amount)).where(
            TrsTransaction.target_wallet_id == wallet_id,
            TrsTransaction.owner_telegram_user_id == user_id,
            TrsTransaction.type == 'transfer'
        )
        trf_in = (await self.session.execute(trf_in_stmt)).scalar() or 0

        return float(initial) + float(inc) - float(exp) - float(trf_out) + float(trf_in)

    async def create_debt(
        self,
        owner_user_id: int,
        counterparty_name: str,
        direction: str,
        amount: float,
        description: str,
        notes: Optional[str] = None
    ) -> TrsDebt:
        counterparty = await self.get_or_create_counterparty(owner_user_id, counterparty_name)
        debt = TrsDebt(
            owner_telegram_user_id=owner_user_id,
            counterparty_id=counterparty.id,
            direction=direction,
            amount=amount,
            description=description,
            status="pending",
            notes=notes
        )
        self.session.add(debt)
        await self.session.commit()
        await self.session.refresh(debt)
        return debt

    async def get_debts_owed(self, user_id: int, status: str = "pending") -> List[TrsDebt]:
        stmt = select(TrsDebt).options(
            joinedload(TrsDebt.counterparty)
        ).where(
            TrsDebt.owner_telegram_user_id == user_id,
            TrsDebt.direction == "I_OWE",
            TrsDebt.status == status
        ).order_by(desc(TrsDebt.created_at))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_debts_to_collect(self, user_id: int, status: str = "pending") -> List[TrsDebt]:

        stmt = select(TrsDebt).options(
            joinedload(TrsDebt.counterparty)
        ).where(
            TrsDebt.owner_telegram_user_id == user_id,
            TrsDebt.direction == "THEY_OWE",
            TrsDebt.status == status
        ).order_by(desc(TrsDebt.created_at))

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_debt_by_id(self, debt_id: int) -> Optional[TrsDebt]:

        stmt = select(TrsDebt).options(
            joinedload(TrsDebt.counterparty)
        ).where(TrsDebt.id == debt_id)

        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def mark_debt_as_paid(
        self,
        debt_id: int,
        transaction_id: Optional[int] = None,
        paid_amount: Optional[float] = None
    ) -> TrsDebt:
        debt = await self.get_debt_by_id(debt_id)
        if not debt:
            raise ValueError(f"Debt {debt_id} tidak ditemukan")

        if debt.status != "pending":
            raise ValueError(f"Debt sudah {debt.status}")

        if paid_amount is None:
            paid_amount = float(debt.amount)

        if paid_amount <= 0:
            raise ValueError("Nominal pembayaran harus lebih dari 0")

        remaining = float(debt.amount) - float(paid_amount)

        if remaining > 0:
            debt.amount = remaining
        else:
            debt.status = "paid"
            debt.paid_at = datetime.now()

        debt.related_transaction_id = transaction_id

        await self.session.commit()
        await self.session.refresh(debt)
        return debt

    async def get_latest_open_debt_with_counterparty(
        self,
        owner_user_id: int,
        counterparty_name: str,
        direction: str = "I_OWE"
    ) -> Optional[TrsDebt]:
        stmt = select(TrsDebt).join(MstCounterparty).options(
            joinedload(TrsDebt.counterparty)
        ).where(
            TrsDebt.owner_telegram_user_id == owner_user_id,
            TrsDebt.direction == direction,
            TrsDebt.status == "pending",
            MstCounterparty.owner_telegram_user_id == owner_user_id,
            MstCounterparty.display_name.ilike(counterparty_name.strip()),
        ).order_by(desc(TrsDebt.created_at)).limit(1)

        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def cancel_debt(self, debt_id: int) -> TrsDebt:
        debt = await self.get_debt_by_id(debt_id)
        if not debt:
            raise ValueError(f"Debt {debt_id} tidak ditemukan")

        if debt.status == "paid":
            raise ValueError("Debt sudah paid, tidak bisa dicancel")

        debt.status = "cancelled"

        await self.session.commit()
        await self.session.refresh(debt)
        return debt
