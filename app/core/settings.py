from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    APP_PORT: int
    TELEGRAM_TOKEN: str
    WEBHOOK_URL: str | None = None

    DATABASE_URL: str = Field(..., alias="DATABASE_URL")

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
