import logging
from typing import Optional

from app.application.services.debt_service import DebtService

logger = logging.getLogger(__name__)


class ManageDebt:
    """
    UseCase: Manage debt (hutang-piutang) operations

    Handles:
    - Create new debt
    - List user's debts and receivables
    - Mark debt as paid
    """

    def __init__(self, debt_service: DebtService):
        self.service = debt_service

    async def create_debt(
        self,
        owner_user_id: int,
        counterparty_name: str,
        direction: str,
        amount: float,
        description: str,
        notes: Optional[str] = None
    ) -> dict:
        """
        UseCase: Create new personal debt record

        Validation:
        - Amount harus > 0
        - Counterparty wajib diisi
        - Direction harus I_OWE atau THEY_OWE
        """
        direction = direction.strip().upper() if direction else ""
        logger.info(f"UseCase: Create debt - owner {owner_user_id} {direction} {counterparty_name} {amount}")

        # Input validation
        if owner_user_id <= 0:
            return {
                "success": False,
                "error": "User ID tidak valid"
            }

        if not counterparty_name or not counterparty_name.strip():
            return {
                "success": False,
                "error": "Nama pihak lawan wajib diisi"
            }

        if direction not in {"I_OWE", "THEY_OWE"}:
            return {
                "success": False,
                "error": "Direction harus I_OWE atau THEY_OWE"
            }

        if amount <= 0:
            return {
                "success": False,
                "error": "Amount harus lebih dari 0"
            }

        if not description or len(description.strip()) == 0:
            return {
                "success": False,
                "error": "Description wajib diisi"
            }

        # Call service
        try:
            result = await self.service.create_debt_record(
                owner_user_id=owner_user_id,
                counterparty_name=counterparty_name,
                direction=direction,
                amount=amount,
                description=description,
                notes=notes
            )

            direction_text = "Anda berhutang ke" if direction == "I_OWE" else "Berhutang ke Anda"
            return {
                "success": True,
                "data": result,
                "message": f"✅ Hutang berhasil dicatat! {direction_text}: {counterparty_name.strip()} - Rp {amount:,.0f}"
            }
        except ValueError as e:
            logger.error(f"Validation error in create_debt: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error in create_debt: {e}")
            return {
                "success": False,
                "error": f"Terjadi kesalahan: {str(e)}"
            }

    async def get_debt_summary(self, user_id: int) -> dict:
        """
        UseCase: Get user's debt summary (hutang + piutang)
        """
        logger.info(f"UseCase: Get debt summary for user {user_id}")

        try:
            # Get formatted summary
            summary_text = await self.service.format_debt_summary(user_id)

            # Get raw data juga
            debts_data = await self.service.get_my_debts(user_id)
            receivables_data = await self.service.get_my_receivables(user_id)

            return {
                "success": True,
                "summary": summary_text,
                "data": {
                    "debts": debts_data,
                    "receivables": receivables_data
                }
            }
        except Exception as e:
            logger.error(f"Error in get_debt_summary: {e}")
            return {
                "success": False,
                "error": f"Gagal mengambil data: {str(e)}"
            }

    async def pay_debt(
        self,
        debt_id: int,
        user_id: int,
        transaction_id: Optional[int] = None,
        paid_amount: Optional[float] = None
    ) -> dict:
        """
        UseCase: Mark debt as paid

        Validation:
        - User harus owner dari catatan debt ini
        - Debt harus status pending
        """
        logger.info(f"UseCase: Pay debt {debt_id} by user {user_id}")

        if debt_id <= 0:
            return {
                "success": False,
                "error": "Debt ID tidak valid"
            }

        if paid_amount is not None and paid_amount <= 0:
            return {
                "success": False,
                "error": "Nominal pembayaran harus lebih dari 0"
            }

        try:
            result = await self.service.mark_as_paid(
                debt_id=debt_id,
                user_id=user_id,
                transaction_id=transaction_id,
                paid_amount=paid_amount
            )

            if result["status"] == "paid":
                message = f"✅ Hutang berhasil dilunasi! Rp {result['paid_amount']:,.0f}"
            else:
                message = (
                    f"✅ Pembayaran hutang dicatat: Rp {result['paid_amount']:,.0f}\n"
                    f"💰 Sisa hutang: Rp {result['remaining_amount']:,.0f}"
                )

            return {
                "success": True,
                "data": result,
                "message": message
            }
        except ValueError as e:
            logger.error(f"Validation error in pay_debt: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error in pay_debt: {e}")
            return {
                "success": False,
                "error": f"Terjadi kesalahan: {str(e)}"
            }
