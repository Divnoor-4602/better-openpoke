"""Simplified configuration management."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parents[1]
ENV_PATH = APP_ROOT / ".env"


def _load_env_file() -> None:
    """Load .env from this app's directory if present."""
    if not ENV_PATH.is_file():
        return

    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_env_file()


DEFAULT_APP_NAME = "General Poke"
DEFAULT_APP_VERSION = "0.3.0"


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


class Settings(BaseModel):
    """Application settings with lightweight env fallbacks."""

    # App metadata
    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_version: str = Field(default=DEFAULT_APP_VERSION)

    # Server runtime
    server_host: str = Field(default=os.getenv("OPENPOKE_HOST", "0.0.0.0"))
    # Railway/Heroku inject PORT; fall back to OPENPOKE_PORT for explicit overrides, then 8001.
    server_port: int = Field(
        default=_env_int("PORT", _env_int("OPENPOKE_PORT", 8001))
    )

    # LLM model selection
    interaction_agent_model: str = Field(default="anthropic/claude-sonnet-4")
    execution_agent_model: str = Field(default="anthropic/claude-haiku-4.5")
    execution_agent_search_model: str = Field(default="anthropic/claude-haiku-4.5")
    thread_title_model: str = Field(default="anthropic/claude-haiku-4.5")
    summarizer_model: str = Field(default="anthropic/claude-sonnet-4")
    email_classifier_model: str = Field(default="anthropic/claude-sonnet-4")

    # Demo auth — single shared password gating all API access. Required.
    demo_password: str = Field(default=os.getenv("DEMO_PASSWORD", ""))

    # Credentials / integrations
    openrouter_api_key: str | None = Field(default=os.getenv("OPENROUTER_API_KEY"))
    composio_google_auth_config_id: str | None = Field(
        default=os.getenv("COMPOSIO_GOOGLE_AUTH_CONFIG_ID")
    )
    composio_api_key: str | None = Field(default=os.getenv("COMPOSIO_API_KEY"))

    # Derived memory search infrastructure. SQLite remains the source of truth.
    pinecone_api_key: str | None = Field(default=os.getenv("PINECONE_API_KEY"))
    pinecone_index_host: str | None = Field(default=os.getenv("PINECONE_INDEX_HOST"))
    memory_search_backend: str = Field(
        default=os.getenv("MEMORY_SEARCH_BACKEND", "pinecone_hybrid")
    )
    memory_index_workers: int = Field(default=_env_int("MEMORY_INDEX_WORKERS", 2))
    memory_index_batch_size: int = Field(
        default=_env_int("MEMORY_INDEX_BATCH_SIZE", 50)
    )
    memory_index_max_attempts: int = Field(
        default=_env_int("MEMORY_INDEX_MAX_ATTEMPTS", 5)
    )
    memory_index_poll_interval_seconds: float = Field(
        default=_env_float("MEMORY_INDEX_POLL_INTERVAL_SECONDS", 2.0)
    )
    memory_debug_log_content: bool = Field(
        default=os.getenv("MEMORY_DEBUG_LOG_CONTENT", "0") == "1"
    )

    # HTTP behaviour
    cors_allow_origins_raw: str = Field(
        default=os.getenv("OPENPOKE_CORS_ALLOW_ORIGINS", "*")
    )
    enable_docs: bool = Field(default=os.getenv("OPENPOKE_ENABLE_DOCS", "1") != "0")
    docs_url: str | None = Field(default=os.getenv("OPENPOKE_DOCS_URL", "/docs"))

    # Summarisation controls
    conversation_summary_threshold: int = Field(default=100)
    conversation_summary_tail_size: int = Field(default=10)
    conversation_recent_entries_limit: int = Field(default=8)

    @property
    def cors_allow_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_allow_origins_raw.strip() in {"", "*"}:
            return ["*"]
        return [
            origin.strip()
            for origin in self.cors_allow_origins_raw.split(",")
            if origin.strip()
        ]

    @property
    def resolved_docs_url(self) -> str | None:
        """Return documentation URL when docs are enabled."""
        return (self.docs_url or "/docs") if self.enable_docs else None

    @property
    def summarization_enabled(self) -> bool:
        """Flag indicating conversation summarisation is active."""
        return self.conversation_summary_threshold > 0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
