import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.settings import settings


def _fernet() -> Fernet:
    if not settings.SUBSCRIPTION_TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("SUBSCRIPTION_TOKEN_ENCRYPTION_KEY belum diisi")

    digest = hashlib.sha256(settings.SUBSCRIPTION_TOKEN_ENCRYPTION_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_token(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_token(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().decrypt(value.encode()).decode()
