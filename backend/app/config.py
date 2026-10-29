from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8002

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "nfpl_access_control"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433

    DATABASE_URL: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            # ensure asyncpg driver is specified
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def sync_database_url(self) -> str:
        # Used for sync operations like alembic or helper scripts
        base_async = self.async_database_url
        if "+asyncpg" in base_async:
            return base_async.replace("postgresql+asyncpg://", "postgresql://", 1)
        return base_async


settings = Settings()
