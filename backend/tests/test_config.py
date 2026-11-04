"""Tests for configuration validation and secret safety."""

from app.config import Settings


def test_default_settings():
    settings = Settings()
    assert settings.APP_ENV == "development"
    assert settings.APP_PORT == 8000
    assert "http://localhost:5173" in settings.CORS_ORIGINS
    assert settings.DATABASE_URL is None
    assert settings.REDIS_URL is None
    assert settings.VULTR_INFERENCE_API_KEY is None


def test_cors_origins_parsing():
    # Comma-separated
    s1 = Settings(CORS_ORIGINS="http://localhost:5173, http://localhost:3000")
    assert s1.CORS_ORIGINS == ["http://localhost:5173", "http://localhost:3000"]

    # JSON array string
    s2 = Settings(CORS_ORIGINS='["http://localhost:5173", "http://127.0.0.1:5173"]')
    assert s2.CORS_ORIGINS == ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Direct list
    s3 = Settings(CORS_ORIGINS=["http://example.com"])
    assert s3.CORS_ORIGINS == ["http://example.com"]


def test_safe_dict_redaction():
    settings = Settings(
        VULTR_INFERENCE_API_KEY="vultr-secret-key-12345",
        DATABASE_URL="postgresql://user:password@localhost:5432/db",
        WORKER_SHARED_SECRET="super-secret-worker-token",
    )
    safe = settings.safe_dict()
    assert safe["VULTR_INFERENCE_API_KEY"] == "********"
    assert safe["DATABASE_URL"] == "********"
    assert safe["WORKER_SHARED_SECRET"] == "********"
    # Ensure unmasked non-sensitive values are retained
    assert safe["APP_PORT"] == 8000

