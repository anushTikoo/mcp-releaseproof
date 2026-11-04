"""Application configuration using Pydantic Settings."""

import json
from typing import Any, List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP ReleaseProof configuration.
    
    Validates application environment settings while keeping external
    infrastructure credentials (DB, Redis, Vultr Inference) optional during Phase 1.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Application Settings
    APP_ENV: str = Field(default="development", description="Application environment")
    APP_HOST: str = Field(default="0.0.0.0", description="Bind host")
    APP_PORT: int = Field(default=8000, description="Bind port")
    PUBLIC_BASE_URL: str = Field(
        default="http://localhost:8000", description="Publicly accessible base URL"
    )
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        description="Allowed CORS origins",
    )

    # Vultr Serverless Inference (Deferred to Phase 2+)
    VULTR_INFERENCE_BASE_URL: Optional[str] = Field(
        default="https://api.vultrinference.com/v1",
        description="Base URL for Vultr Serverless Inference",
    )
    VULTR_INFERENCE_API_KEY: Optional[str] = Field(
        default=None, description="Vultr Serverless Inference API Key"
    )
    VULTR_INFERENCE_MODEL: Optional[str] = Field(
        default=None, description="Selected model ID from Vultr catalogue"
    )

    # Database (Deferred to Phase 2+)
    DATABASE_URL: Optional[str] = Field(
        default=None, description="PostgreSQL connection string"
    )

    # Redis (Deferred to Phase 2+)
    REDIS_URL: Optional[str] = Field(
        default=None, description="Redis connection string"
    )

    # Worker Authentication (Deferred to Phase 2+)
    WORKER_SHARED_SECRET: Optional[str] = Field(
        default=None, description="Shared secret for worker authentication"
    )

    # Artifact Storage
    ARTIFACT_STORAGE_MODE: str = Field(
        default="local", description="Artifact storage mode (local or s3)"
    )
    ARTIFACT_ROOT: str = Field(
        default="./data/artifacts", description="Root directory for local artifacts"
    )

    # Limits
    MAX_REPOSITORY_SIZE_MB: int = 200
    MAX_SCAN_DURATION_SECONDS: int = 600
    MAX_SCENARIOS_PER_SCAN: int = 10
    MAX_TOOL_CALLS_PER_SCAN: int = 50
    MAX_ARTIFACT_SIZE_MB: int = 50

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value]
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(v).strip() for v in parsed]
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in value.split(",") if item.strip()]
        return ["http://localhost:5173"]

    def safe_dict(self) -> dict[str, Any]:
        """Return non-sensitive configuration parameters for logging or inspection."""
        sensitive_keys = {
            "VULTR_INFERENCE_API_KEY",
            "WORKER_SHARED_SECRET",
            "DATABASE_URL",
            "REDIS_URL",
        }
        data = self.model_dump()
        for key in sensitive_keys:
            if key in data and data[key] is not None:
                data[key] = "********"
        return data


# Lazy-loaded settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

