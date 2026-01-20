"""Configuration management from environment variables"""

import os
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Dict, Any, List


def _load_plugins_config() -> Dict[str, Any]:
    """Load plugins configuration from YAML file with environment variable substitution"""
    config_path = Path("config/plugins.yaml")
    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # Get plugins section
    plugins = config.get("plugins", {})

    # Substitute environment variables in format ${VAR_NAME}
    def substitute_env(obj):
        if isinstance(obj, str):
            if obj.startswith("${") and obj.endswith("}"):
                var_name = obj[2:-1]
                return os.getenv(var_name, obj)
            return obj
        elif isinstance(obj, dict):
            return {k: substitute_env(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [substitute_env(item) for item in obj]
        return obj

    return substitute_env(plugins)


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

    # Plugin Config (from YAML) - will be loaded by validator
    plugins_config: Dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def load_plugins_from_yaml(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Load plugins configuration from YAML file"""
        if "plugins_config" not in data or not data["plugins_config"]:
            data["plugins_config"] = _load_plugins_config()
        return data

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
