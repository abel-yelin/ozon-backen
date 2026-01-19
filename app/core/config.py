"""Configuration management from environment variables"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, List


class Settings(BaseSettings):
    """Application configuration loaded from environment variables"""

    # R2 Configuration
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str
    r2_public_url: str

    # Service Auth
    python_service_api_key: str

    # CORS Configuration (comma-separated list for production)
    cors_origins: str = "*"  # e.g., "https://example.com,https://app.example.com"

    # Environment
    environment: str = "development"
    debug: bool = False

    # Plugin Config (from YAML)
    plugins_config: Dict[str, Any] = {}

    @property
    def cors_origins_list(self) -> List[str]:
        """Convert CORS origins string to list"""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
