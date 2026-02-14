import logging
from typing import List, Optional

from app.domain.finance.ports import FinanceRepoPort
from app.infrastructure.db.models import TrsDebt

logger = logging.getLogger(__name__)


class DebtService:
    def __init__(self, repo: FinanceRepoPort):
        self.repo = repo

    async def create_debt_record(
        self,
        creditor_user_id: int,
        debtor_user_id: int,
        amount: float,
        description: str,
        notes: Optional[str] = None
    ) -> dict:
        """
        Create hutang-piutang record

        Args:
            creditor_user_id: User yang bayar duluan (punya piutang)
            debtor_user_id: User yang ngutang (punya hutang)
            amount: Jumlah hutang
            description: Deskripsi singkat
            notes: Catatan tambahan (optional)

        Returns:
            Dict dengan debt info
        """
        # Validasi
        if creditor_user_id == debtor_user_id:
            raise ValueError("Tidak bisa create hutang ke diri sendiri")

        if amount <= 0:
            raise ValueError("Amount harus lebih dari 0")

        # Create debt
        debt = await self.repo.create_debt(
            creditor_user_id=creditor_user_id,
            debtor_user_id=debtor_user_id,
            amount=amount,
            description=description,
            notes=notes
        )

        logger.info(f"Debt created: {debt.id} - {debtor_user_id} owes {creditor_user_id} {amount}")

        return {
            "debt_id": debt.id,
            "creditor_user_id": debt.creditor_user_id,
            "debtor_user_id": debt.debtor_user_id,
            "amount": float(debt.amount),
            "description": debt.description,
            "status": debt.status,
            "created_at": debt.created_at.isoformat()
        }

    async def get_my_debts(self, user_id: int) -> dict:
        """
        Get hutang yang dimiliki user (yang harus dibayar)
        """
        debts = await self.repo.get_debts_owed(user_id, status="pending")

        total_debt = sum(float(d.amount) for d in debts)

        debt_list = []
        for debt in debts:
            debt_list.append({
                "debt_id": debt.id,
                "creditor_name": debt.creditor.first_name if debt.creditor else "Unknown",
                "creditor_id": debt.creditor_user_id,
                "amount": float(debt.amount),
                "description": debt.description,
                "created_at": debt.created_at.isoformat(),
                "notes": debt.notes
            })

        return {
            "total_debt": total_debt,
            "count": len(debts),
            "debts": debt_list
        }

    async def get_my_receivables(self, user_id: int) -> dict:
        """
        Get piutang yang dimiliki user (yang harus dibayar ke user)
        """
        debts = await self.repo.get_debts_to_collect(user_id, status="pending")

        total_receivable = sum(float(d.amount) for d in debts)

        receivable_list = []
        for debt in debts:
            receivable_list.append({
                "debt_id": debt.id,
                "debtor_name": debt.debtor.first_name if debt.debtor else "Unknown",
                "debtor_id": debt.debtor_user_id,
                "amount": float(debt.amount),
                "description": debt.description,
                "created_at": debt.created_at.isoformat(),
                "notes": debt.notes
            })

        return {
            "total_receivable": total_receivable,
            "count": len(debts),
            "receivables": receivable_list
        }

    async def mark_as_paid(
        self,
        debt_id: int,
        user_id: int,
        transaction_id: Optional[int] = None
    ) -> dict:
        """
        Mark debt sebagai lunas

        Args:
            debt_id: ID hutang
            user_id: User yang melakukan action (untuk validasi)
            transaction_id: Optional link ke transaction pembayaran
        """
        # Get debt untuk validasi
        debt = await self.repo.get_debt_by_id(debt_id)

        if not debt:
            raise ValueError(f"Debt {debt_id} tidak ditemukan")

        # Validasi: hanya creditor atau debtor yang bisa mark as paid
        if user_id not in [debt.creditor_user_id, debt.debtor_user_id]:
            raise ValueError("Anda tidak punya akses untuk debt ini")

        # Mark as paid
        updated_debt = await self.repo.mark_debt_as_paid(debt_id, transaction_id)

        logger.info(f"Debt {debt_id} marked as paid by user {user_id}")

        return {
            "debt_id": updated_debt.id,
            "status": updated_debt.status,
            "paid_at": updated_debt.paid_at.isoformat() if updated_debt.paid_at else None,
            "amount": float(updated_debt.amount)
        }

    async def format_debt_summary(self, user_id: int) -> str:
        """
        Format debt summary untuk display (Telegram/HTTP)
        """
        debts_data = await self.get_my_debts(user_id)
        receivables_data = await self.get_my_receivables(user_id)

        # Format output
        output = "💰 **Ringkasan Hutang-Piutang**\n\n"

        # Hutang (yang harus dibayar)
        output += f"🔴 **Hutang Saya**: Rp {debts_data['total_debt']:,.0f}\n"
        if debts_data['debts']:
            for debt in debts_data['debts'][:5]:  # Max 5
                output += f"  • {debt['creditor_name']}: Rp {debt['amount']:,.0f}\n"
                output += f"    {debt['description']}\n"
            if debts_data['count'] > 5:
                output += f"  ... dan {debts_data['count'] - 5} hutang lainnya\n"
        else:
            output += "  ✅ Tidak ada hutang\n"

        output += "\n"

        # Piutang (yang harus dibayar ke kita)
        output += f"🟢 **Piutang Saya**: Rp {receivables_data['total_receivable']:,.0f}\n"
        if receivables_data['receivables']:
            for rec in receivables_data['receivables'][:5]:  # Max 5
                output += f"  • {rec['debtor_name']}: Rp {rec['amount']:,.0f}\n"
                output += f"    {rec['description']}\n"
            if receivables_data['count'] > 5:
                output += f"  ... dan {receivables_data['count'] - 5} piutang lainnya\n"
        else:
            output += "  📭 Tidak ada piutang\n"

        output += "\n"
        output += f"**Net**: Rp {receivables_data['total_receivable'] - debts_data['total_debt']:,.0f}"

        return output
