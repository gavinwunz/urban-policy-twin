"""Runtime configuration.

Values are read from the environment (see ``.env.example``). No secrets are
committed; missing values fall back to safe defaults so the app always boots.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from environment variables / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        # Renamed from URBAN_ with the rebrand. pydantic-settings reads exactly
        # one prefix, so an existing local .env must be renamed too — see
        # .env.example.
        env_prefix="GOVSIM_",
        extra="ignore",
    )

    app_name: str = "GOV SIM"
    tagline: str = (
        "GOV SIM is a policy simulation environment that lets governments "
        "test, stress-test, debate, amend and explore policies before they "
        "are deployed in the real world."
    )
    version: str = "0.2.0"
    environment: str = "development"

    # --- persistence ----------------------------------------------------
    # A local mongod is the default. Every code path must degrade gracefully
    # when it is not running (see app/db/mongo.py).
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db: str = "govsim"
    mongo_timeout_ms: int = 800

    # Comma-separated list of allowed CORS origins for the frontend.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # LLM key is optional at boot. Code paths that need it must degrade to a
    # rule-based fallback when it is absent (see AGENT_LOOP.md). Never hardcode.
    llm_api_key: str = ""
    # Which provider/model to use when a key is present. The compiler only uses
    # the LLM for language structuring, never numeric effects (SPEC §34).
    llm_provider: str = "anthropic"
    llm_model: str = "claude-3-5-haiku-latest"
    llm_base_url: str = "https://api.anthropic.com"
    llm_timeout_s: float = 20.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()
