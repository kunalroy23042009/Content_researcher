"""
Typed application settings loaded from .env via pydantic-settings.

Usage:
    from app.config import settings
    print(settings.YOUTUBE_API_KEY)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """All external API credentials and configuration for Creator Content Radar."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # External APIs
    YOUTUBE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    AI_PROVIDER: str = "auto"  # auto, gemini, groq, openrouter

    # Reddit API
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "creator-content-radar/0.1"

    # JWT Auth
    SECRET_KEY: str = "dev-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    ALGORITHM: str = "HS256"

    # Database
    DATABASE_URL: str = "sqlite:///./data/cache.db"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_PRO_MONTHLY: str = ""
    STRIPE_PRICE_BUSINESS_MONTHLY: str = ""

    # App
    APP_URL: str = "http://localhost:8000"


    @field_validator("YOUTUBE_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY")
    @classmethod
    def strip_quotes(cls, v: str) -> str:
        """Strip surrounding quotes that may come from env files."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            if v.startswith("'") and v.endswith("'"):
                v = v[1:-1]
        return v


# Singleton – import this everywhere
settings = Settings()
