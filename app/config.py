from functools import lru_cache

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tupa"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://tupa:tupa@localhost:5432/tupa"
    service_token: str = "change-me"
    admin_username: str = "admin"
    admin_password: str | None = None
    jwt_private_key: str | None = None
    jwt_public_key: str | None = None
    jwt_key_id: str = "tupa-dev-1"
    jwt_issuer: str = "tupa"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("database_url")
    @classmethod
    def normalize_cloud_database_url(cls, value: str) -> str:
        parts = urlsplit(value)
        scheme = {
            "postgres": "postgresql+asyncpg",
            "postgresql": "postgresql+asyncpg",
        }.get(parts.scheme, parts.scheme)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)
        if sslmode and "ssl" not in query:
            query["ssl"] = (
                "require" if sslmode in {"require", "verify-ca", "verify-full"} else sslmode
            )
        return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment == "production" and self.service_token == "change-me":
            raise ValueError("SERVICE_TOKEN must be configured in production")
        return self

    @property
    def effective_admin_password(self) -> str:
        return self.admin_password or self.service_token


@lru_cache
def get_settings() -> Settings:
    return Settings()
