from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- LLM & AI Providers ---
    LLM_PROVIDER: str
    GOOGLE_API_KEY: str | None = None
    OLLAMA_BASE_URL: str
    OLLAMA_TEXT_MODEL: str
    OLLAMA_VISION_MODEL: str
    OLLAMA_TIMEOUT_SECONDS: float

    # --- App & Telegram ---
    APP_PORT: int = 8000
    TELEGRAM_TOKEN: str
    WEBHOOK_URL: str | None = None

    # --- Database ---
    DATABASE_URL: str = Field(..., alias="DATABASE_URL")

    # --- Membership ---
    # Kode plan yang otomatis di-assign ke user baru saat /start.
    # Upgrade ke plan berbayar dilakukan lewat dashboard, bukan lewat bot ini.
    DEFAULT_FREE_PLAN_CODE: str

    # --- Subscription Email Scanner ---
    GMAIL_OAUTH_CLIENT_ID: str | None = None
    GMAIL_OAUTH_CLIENT_SECRET: str | None = None
    GMAIL_OAUTH_REDIRECT_URI: str | None = None
    GMAIL_OAUTH_SCOPES: str = "https://www.googleapis.com/auth/gmail.readonly"
    SUBSCRIPTION_TOKEN_ENCRYPTION_KEY: str | None = None
    SUBSCRIPTION_SCAN_MAX_EMAILS: int = 10

    # --- Midtrans ---
    MIDTRANS_SERVER_KEY: str
    MIDTRANS_CLIENT_KEY: str
    MIDTRANS_IS_PRODUCTION: bool = False

    # --- Redis & Queue ---
    REDIS_URL: str
    TELEGRAM_QUEUE_WORKERS: int
    TELEGRAM_UPDATE_DEDUPE_TTL_SECONDS: int
    TELEGRAM_USER_QUEUE_LOCK_TTL_SECONDS: int

    # --- Langfuse (Observability) ---
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_BASE_URL: str
    LANGFUSE_TEST_INTERFACE_ENABLED: bool
    LANGFUSE_TEST_INTERFACE_TOKEN: str | None = None

    @property
    def database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True
    )

settings = Settings()
