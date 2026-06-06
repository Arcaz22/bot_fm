import logging
from typing import Optional

from app.domain.finance.ports import FinanceRepoPort
logger = logging.getLogger(__name__)


class DebtService:
    def __init__(self, repo: FinanceRepoPort):
        self.repo = repo

    async def create_debt_record(
        self,
        owner_user_id: int,
        counterparty_name: str,
        direction: str,
        amount: float,
        description: str,
        notes: Optional[str] = None
    ) -> dict:
        """
        Create personal hutang-piutang record.

        Args:
            owner_user_id: User pemilik catatan
            counterparty_name: Nama pihak lawan, disimpan sebagai kontak personal
            direction: I_OWE jika owner hutang, THEY_OWE jika pihak lawan hutang ke owner
            amount: Jumlah hutang
            description: Deskripsi singkat
            notes: Catatan tambahan (optional)

        Returns:
            Dict dengan debt info
        """
        # Validasi
        direction = direction.strip().upper() if direction else ""

        if owner_user_id <= 0:
            raise ValueError("User ID tidak valid")

        if not counterparty_name or not counterparty_name.strip():
            raise ValueError("Nama pihak lawan wajib diisi")

        if direction not in {"I_OWE", "THEY_OWE"}:
            raise ValueError("Direction harus I_OWE atau THEY_OWE")

        if amount <= 0:
            raise ValueError("Amount harus lebih dari 0")

        # Create debt
        debt = await self.repo.create_debt(
            owner_user_id=owner_user_id,
            counterparty_name=counterparty_name,
            direction=direction,
            amount=amount,
            description=description,
            notes=notes
        )

        logger.info(f"Debt created: {debt.id} - owner {owner_user_id} {direction} {counterparty_name} {amount}")

        return {
            "debt_id": debt.id,
            "owner_user_id": debt.owner_telegram_user_id,
            "counterparty_id": debt.counterparty_id,
            "counterparty_name": counterparty_name.strip(),
            "direction": debt.direction,
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
                "counterparty_name": debt.counterparty.display_name if debt.counterparty else "Unknown",
                "counterparty_id": debt.counterparty_id,
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
                "counterparty_name": debt.counterparty.display_name if debt.counterparty else "Unknown",
                "counterparty_id": debt.counterparty_id,
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
        transaction_id: Optional[int] = None,
        paid_amount: Optional[float] = None
    ) -> dict:
        """
        Mark debt sebagai lunas atau bayar sebagian.

        Args:
            debt_id: ID hutang
            user_id: Owner catatan debt
            transaction_id: Optional link ke transaction pembayaran
            paid_amount: Optional nominal pembayaran. Jika lebih kecil dari debt,
                sisa debt tetap pending.
        """
        # Get debt untuk validasi
        debt = await self.repo.get_debt_by_id(debt_id)

        if not debt:
            raise ValueError(f"Debt {debt_id} tidak ditemukan")

        # Debt adalah ledger personal. Hanya owner catatan yang bisa mengubah status.
        if user_id != debt.owner_telegram_user_id:
            raise ValueError("Anda tidak punya akses untuk debt ini")

        original_amount = float(debt.amount)
        updated_debt = await self.repo.mark_debt_as_paid(debt_id, transaction_id, paid_amount)

        logger.info(f"Debt {debt_id} paid by user {user_id}")

        return {
            "debt_id": updated_debt.id,
            "status": updated_debt.status,
            "paid_at": updated_debt.paid_at.isoformat() if updated_debt.paid_at else None,
            "paid_amount": float(paid_amount if paid_amount is not None else original_amount),
            "remaining_amount": 0 if updated_debt.status == "paid" else float(updated_debt.amount),
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
                output += f"  • {debt['counterparty_name']}: Rp {debt['amount']:,.0f}\n"
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
                output += f"  • {rec['counterparty_name']}: Rp {rec['amount']:,.0f}\n"
                output += f"    {rec['description']}\n"
            if receivables_data['count'] > 5:
                output += f"  ... dan {receivables_data['count'] - 5} piutang lainnya\n"
        else:
            output += "  📭 Tidak ada piutang\n"

        output += "\n"
        output += f"**Net**: Rp {receivables_data['total_receivable'] - debts_data['total_debt']:,.0f}"

        return output
