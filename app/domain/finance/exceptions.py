class FinanceError(Exception):
    """Base error untuk urusan keuangan"""
    pass

class InsufficientBalanceError(FinanceError):
    """Dilempar ketika mau expense/transfer tapi duit gak cukup"""
    pass

class WalletNotFoundError(FinanceError):
    """Dilempar ketika user nyebut wallet yang gak ada di DB"""
    pass

class InvalidTransactionError(FinanceError):
    """Error validasi umum (misal amount negatif)"""
    pass
