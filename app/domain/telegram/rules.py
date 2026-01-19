from .entities import TelegramUser

class TelegramRuleError(ValueError):
    pass

def ensure_active(user: TelegramUser) -> None:
    if not user.is_active:
        raise TelegramRuleError("User tidak aktif, tidak bisa memproses pesan.")

def reset_to_idle(user: TelegramUser) -> None:
    user.change_state("IDLE", {})
