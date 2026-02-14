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
        creditor_user_id: int,
        debtor_user_id: int,
        amount: float,
        description: str,
        notes: Optional[str] = None
    ) -> dict:
        """
        UseCase: Create new debt record

        Validation:
        - Amount harus > 0
        - Creditor != Debtor
        """
        logger.info(f"UseCase: Create debt - {debtor_user_id} owes {creditor_user_id} {amount}")

        # Input validation
        if creditor_user_id <= 0 or debtor_user_id <= 0:
            return {
                "success": False,
                "error": "User ID tidak valid"
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
                creditor_user_id=creditor_user_id,
                debtor_user_id=debtor_user_id,
                amount=amount,
                description=description,
                notes=notes
            )

            return {
                "success": True,
                "data": result,
                "message": f"✅ Hutang berhasil dicatat! {amount:,.0f}"
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
        transaction_id: Optional[int] = None
    ) -> dict:
        """
        UseCase: Mark debt as paid

        Validation:
        - User harus creditor atau debtor dari debt ini
        - Debt harus status pending
        """
        logger.info(f"UseCase: Pay debt {debt_id} by user {user_id}")

        if debt_id <= 0:
            return {
                "success": False,
                "error": "Debt ID tidak valid"
            }

        try:
            result = await self.service.mark_as_paid(
                debt_id=debt_id,
                user_id=user_id,
                transaction_id=transaction_id
            )

            return {
                "success": True,
                "data": result,
                "message": f"✅ Hutang berhasil dilunasi! Rp {result['amount']:,.0f}"
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
