"""Configuration management from environment variables"""

import os
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, Field
from typing import Dict, Any, List


_ENV_FILES = (".env", ".env.local")


def _load_env_defaults() -> None:
    env_values: Dict[str, str] = {}
    for filename in _ENV_FILES:
        path = Path(filename)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if (value.startswith("\"") and value.endswith("\"")) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            env_values[key] = value

    for key, value in env_values.items():
        os.environ.setdefault(key, value)


def _load_plugins_config() -> Dict[str, Any]:
    """Load plugins configuration from YAML file with environment variable substitution"""
    _load_env_defaults()
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

    # Ozon image push configuration
    ozon_push_timeout: int = Field(
        default=30,
        description="Ozon API timeout in seconds for image push operations"
    )
    ozon_push_max_retries: int = Field(
        default=2,
        description="Maximum retry attempts for failed image push requests"
    )
    ozon_push_validate_urls: bool = Field(
        default=True,
        description="Whether to validate R2 URLs before sending to Ozon API"
    )

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
