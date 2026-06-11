from app.config import Settings


def test_normalizes_cloud_postgres_url_for_asyncpg():
    settings = Settings(
        _env_file=None,
        database_url=(
            "postgresql://user:password@cloud.example.com/tupa"
            "?sslmode=require&channel_binding=require"
        ),
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:password@cloud.example.com/tupa?ssl=require"
    )


def test_preserves_asyncpg_cloud_url():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:password@cloud.example.com/tupa?ssl=require",
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:password@cloud.example.com/tupa?ssl=require"
    )


def test_preserves_url_encoded_cloud_password():
    settings = Settings(
        _env_file=None,
        database_url="postgres://user:p%40ss%25word@cloud.example.com/tupa?sslmode=require",
    )

    assert "p%40ss%25word" in settings.database_url
    assert settings.database_url.startswith("postgresql+asyncpg://")
