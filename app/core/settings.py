from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    APP_PORT: int
    TELEGRAM_TOKEN: str
    WEBHOOK_URL: str | None = None

    DATABASE_URL: str = Field(..., alias="DATABASE_URL")

    AI_FREE_QUOTA: int
    AI_WHITELIST_USER_IDS: str | None = None

    REDIS_URL: str = "redis://localhost:6379/0"
    TELEGRAM_QUEUE_WORKERS: int = 2
    TELEGRAM_UPDATE_DEDUPE_TTL_SECONDS: int = 604800
    TELEGRAM_USER_QUEUE_LOCK_TTL_SECONDS: int = 300

    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_BASE_URL: str = "http://localhost:3000"
    LANGFUSE_TEST_INTERFACE_ENABLED: bool = False
    LANGFUSE_TEST_INTERFACE_TOKEN: str | None = None

    @property
    def database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def ai_whitelist_ids(self) -> set[int]:
        if not self.AI_WHITELIST_USER_IDS:
            return set()
        ids: set[int] = set()
        for part in self.AI_WHITELIST_USER_IDS.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except ValueError:
                continue
        return ids

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True
    )

settings = Settings()
