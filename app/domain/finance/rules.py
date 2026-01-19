from app.domain.finance.exceptions import InsufficientBalanceError, InvalidTransactionError

def validate_transaction_amount(amount: float):
    if amount <= 0:
        raise InvalidTransactionError("Nominal transaksi harus lebih dari 0!")

def ensure_sufficient_balance(current_balance: float, expense_amount: float):
    """
    Cek apakah saldo cukup.
    Ingat: Logic ini opsional. Kadang kita mau membolehkan saldo minus (hutang).
    Tapi kalau mau strict, pakai ini.
    """
    if current_balance < expense_amount:
        raise InsufficientBalanceError(
            f"Saldo tidak cukup! Sisa: {current_balance:,.0f}, Mau keluar: {expense_amount:,.0f}"
        )

def normalize_wallet_name(raw_name: str) -> str:
    """Standardisasi nama wallet (misal user ketik 'bca ' jadi 'BCA')"""
    if not raw_name:
        return "Cash"
    return raw_name.strip().title()
