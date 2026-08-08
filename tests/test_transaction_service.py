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


class WrongAmountIncomeLLM:
    async def parse_transaction(self, text):
        return {
            "amount": 580_000,
            "category": "Salary",
            "wallet_name": "BCA",
            "target_wallet_name": None,
            "description": "Gaji bulan agustus",
            "transaction_type": "INCOME",
            "debt_action": "NONE",
            "counterparty_name": None,
        }


class FakeRepo:
    def __init__(self):
        self.wallets = {
            "BCA": SimpleNamespace(id=1, name="BCA", initial_balance=0)
        }
        self.created_transaction = None
        self.created_category = None
        self.categories = {}
        self.transactions = []

    async def get_wallet_by_name(self, user_id, name):
        return next(
            (
                wallet
                for wallet_name, wallet in self.wallets.items()
                if wallet_name.lower() == name.lower()
            ),
            None,
        )

    async def create_wallet(self, user_id, name, initial_balance=0):
        wallet = SimpleNamespace(id=len(self.wallets) + 1, name=name, initial_balance=initial_balance)
        self.wallets[name] = wallet
        return wallet

    async def set_wallet_initial_balance(self, user_id, wallet_id, initial_balance):
        wallet = next(wallet for wallet in self.wallets.values() if wallet.id == wallet_id)
        wallet.initial_balance = initial_balance
        return wallet

    async def get_wallet_balance(self, wallet_id, user_id):
        wallet = next(wallet for wallet in self.wallets.values() if wallet.id == wallet_id)
        balance = wallet.initial_balance
        for transaction in self.transactions:
            if transaction["wallet_id"] == wallet_id:
                if transaction["type"] == "income":
                    balance += transaction["amount"]
                elif transaction["type"] == "expense":
                    balance -= transaction["amount"]
                elif transaction["type"] == "transfer":
                    balance -= transaction["amount"]

            if transaction.get("target_wallet_id") == wallet_id and transaction["type"] == "transfer":
                balance += transaction["amount"]
        return balance

    async def get_category_by_name(self, user_id, name, category_type):
        return self.categories.get((name.lower(), category_type))

    async def create_category(self, user_id, name, category_type):
        category = SimpleNamespace(id=len(self.categories) + 1, name=name, type=category_type)
        self.categories[(name.lower(), category_type)] = category
        self.created_category = category
        return category

    async def create_transaction(self, **kwargs):
        self.created_transaction = kwargs
        self.transactions.append(kwargs)
        return SimpleNamespace(id=len(self.transactions))

    async def get_total_assets(self, user_id):
        total = 0
        for wallet in self.wallets.values():
            total += await self.get_wallet_balance(wallet.id, user_id)
        return total


class TestCashWithdrawal:
    async def test_cash_withdrawal_is_transfer_to_cash_wallet(self):
        repo = FakeRepo()
        service = TransactionService(FakeLLM(), repo)

        result = await service.process_natural_language(
            123,
            "Tarik tunai buat pegangan cash 500k",
        )

        assert "🔄" in result
        assert "BCA ➡️ Cash" in result
        assert "Cash" in repo.wallets
        assert repo.created_transaction["type"] == "transfer"
        assert repo.created_transaction["target_wallet_id"] == repo.wallets["Cash"].id


class TestBalanceMigration:
    async def test_balance_migration_parses_k_suffix_with_large_number(self):
        repo = FakeRepo()
        service = TransactionService(FakeLLM(), repo)

        result = await service.process_natural_language(
            123,
            "Setup wallet gopay 27840k",
        )

        assert "Saldo Wallet Diatur" in result
        assert repo.wallets["Gopay"].initial_balance == 27_840_000
        assert repo.created_transaction is None

    async def test_balance_migration_parses_dot_thousands_without_suffix(self):
        repo = FakeRepo()
        service = TransactionService(FakeLLM(), repo)

        result = await service.process_natural_language(
            123,
            "Setup wallet gopay 27.840",
        )

        assert "Saldo Wallet Diatur" in result
        assert repo.wallets["Gopay"].initial_balance == 27_840
        assert repo.created_transaction is None

    async def test_balance_migration_creates_wallet_without_transaction(self):
        repo = FakeRepo()
        service = TransactionService(FakeLLM(), repo)

        result = await service.process_natural_language(
            123,
            "saldo gopay 20k",
        )

        assert "Saldo Wallet Diatur" in result
        assert "transfer dari wallet lain" in result
        assert repo.wallets["Gopay"].initial_balance == 20_000
        assert repo.created_transaction is None

    async def test_balance_migration_adjusts_existing_wallet_to_target_balance(self):
        repo = FakeRepo()
        repo.wallets["Gopay"] = SimpleNamespace(id=2, name="Gopay", initial_balance=5_000)
        service = TransactionService(FakeLLM(), repo)

        result = await service.process_natural_language(
            123,
            "set saldo gopay 20k",
        )

        assert "Saldo Wallet Diatur" in result
        assert repo.wallets["Gopay"].initial_balance == 20_000
        assert repo.created_transaction is None


class TestIncomeParsing:
    async def test_income_uses_deterministic_amount_hint_over_llm_amount(self):
        repo = FakeRepo()
        service = TransactionService(WrongAmountIncomeLLM(), repo)

        result = await service.process_natural_language(
            123,
            "Gaji bulan agustus 5.8 jt",
        )

        assert "Transaksi Tercatat" in result
        assert repo.created_transaction["type"] == "income"
        assert repo.created_transaction["amount"] == 5_800_000

    async def test_income_prefers_suffixed_amount_when_text_has_other_numbers(self):
        repo = FakeRepo()
        service = TransactionService(WrongAmountIncomeLLM(), repo)

        result = await service.process_natural_language(
            123,
            "Gaji bulan 8 5.8 jt",
        )

        assert "Transaksi Tercatat" in result
        assert repo.created_transaction["amount"] == 5_800_000


class SpecificCategoryLLM:
    async def parse_transaction(self, text):
        return {
            "amount": 1_000_000,
            "category": "Vacation",
            "wallet_name": "BCA",
            "target_wallet_name": None,
            "description": "Liburan ke Bandung",
            "transaction_type": "EXPENSE",
            "debt_action": "NONE",
            "counterparty_name": None,
        }


class TestSimpleCategories:
    async def test_specific_llm_category_falls_back_to_other(self):
        repo = FakeRepo()
        service = TransactionService(SpecificCategoryLLM(), repo)

        result = await service.process_natural_language(
            123,
            "Liburan ke Bandung 1jt dari BCA",
        )

        assert "Transaksi Tercatat" in result
        assert repo.created_category.name == "Other"


class SavingsInvestmentLLM:
    async def parse_transaction(self, text):
        return {
            "amount": 1,
            "category": "Other",
            "wallet_name": "BCA",
            "target_wallet_name": None,
            "description": text[:50],
            "transaction_type": "EXPENSE",
            "debt_action": "NONE",
            "counterparty_name": None,
        }


class TestSavingsAndInvestmentModel:
    async def test_personal_savings_defaults_to_transfer_to_tabungan(self):
        repo = FakeRepo()
        repo.wallets["BCA"].initial_balance = 1_000_000
        service = TransactionService(SavingsInvestmentLLM(), repo)

        before_assets = await repo.get_total_assets(123)
        result = await service.process_natural_language(123, "nabung 500rb")
        after_assets = await repo.get_total_assets(123)

        assert "🔄" in result
        assert "Tabungan" in repo.wallets
        assert repo.created_transaction["type"] == "transfer"
        assert repo.created_transaction["amount"] == 500_000
        assert repo.created_transaction["target_wallet_id"] == repo.wallets["Tabungan"].id
        assert repo.created_category.name == "Savings"
        assert before_assets == after_assets

    async def test_rdn_deposit_is_investment_transfer_to_rdn(self):
        repo = FakeRepo()
        repo.wallets["BCA"].initial_balance = 3_000_000
        service = TransactionService(SavingsInvestmentLLM(), repo)

        before_assets = await repo.get_total_assets(123)
        result = await service.process_natural_language(123, "setor RDN 2jt dari BCA")
        after_assets = await repo.get_total_assets(123)

        assert "🔄" in result
        assert "RDN" in repo.wallets
        assert repo.created_transaction["type"] == "transfer"
        assert repo.created_transaction["target_wallet_id"] == repo.wallets["RDN"].id
        assert repo.created_category.name == "Investment"
        assert before_assets == after_assets

    async def test_stock_investment_without_target_uses_investasi_wallet(self):
        repo = FakeRepo()
        service = TransactionService(SavingsInvestmentLLM(), repo)

        result = await service.process_natural_language(123, "investasi saham 1jt dari BCA")

        assert "🔄" in result
        assert "Investasi" in repo.wallets
        assert repo.created_transaction["type"] == "transfer"
        assert repo.created_transaction["target_wallet_id"] == repo.wallets["Investasi"].id
        assert repo.created_category.name == "Investment"

    async def test_joint_savings_to_other_person_is_expense(self):
        repo = FakeRepo()
        repo.wallets["BCA"].initial_balance = 2_000_000
        service = TransactionService(SavingsInvestmentLLM(), repo)

        before_assets = await repo.get_total_assets(123)
        result = await service.process_natural_language(
            123,
            "transfer 1jt ke tabungan bersama Sari dari BCA",
        )
        after_assets = await repo.get_total_assets(123)

        assert "🔴" in result
        assert repo.created_transaction["type"] == "expense"
        assert repo.created_transaction["target_wallet_id"] is None
        assert repo.created_category.name == "Joint Savings"
        assert before_assets - after_assets == 1_000_000
