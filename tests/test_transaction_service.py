import unittest
from types import SimpleNamespace

from app.application.services.transaction_service import TransactionService


class FakeLLM:
    async def parse_transaction(self, text):
        return {
            "amount": 500_000,
            "category": "Cash Withdrawal",
            "wallet_name": "BCA",
            "target_wallet_name": None,
            "description": "Tarik tunai buat pegangan cash",
            "transaction_type": "EXPENSE",
            "debt_action": "NONE",
            "counterparty_name": None,
        }


class FakeRepo:
    def __init__(self):
        self.wallets = {"BCA": SimpleNamespace(id=1, name="BCA")}
        self.created_transaction = None

    async def get_wallet_by_name(self, user_id, name):
        return next(
            (wallet for wallet_name, wallet in self.wallets.items() if wallet_name.lower() == name.lower()),
            None,
        )

    async def create_wallet(self, user_id, name, initial_balance=0):
        wallet = SimpleNamespace(id=len(self.wallets) + 1, name=name)
        self.wallets[name] = wallet
        return wallet

    async def get_category_by_name(self, user_id, name, category_type):
        return None

    async def create_category(self, user_id, name, category_type):
        return SimpleNamespace(id=1, name=name)

    async def create_transaction(self, **kwargs):
        self.created_transaction = kwargs
        return SimpleNamespace(id=1)


class CashWithdrawalTest(unittest.IsolatedAsyncioTestCase):
    async def test_cash_withdrawal_is_transfer_to_cash_wallet(self):
        repo = FakeRepo()
        service = TransactionService(FakeLLM(), repo)

        result = await service.process_natural_language(
            123, "Tarik tunai buat pegangan cash 500k"
        )

        self.assertIn("🔄", result)
        self.assertIn("BCA ➡️ Cash", result)
        self.assertIn("Cash", repo.wallets)
        self.assertEqual("transfer", repo.created_transaction["type"])
        self.assertEqual(repo.wallets["Cash"].id, repo.created_transaction["target_wallet_id"])


if __name__ == "__main__":
    unittest.main()
