"""
Typed application settings loaded from .env via pydantic-settings.

Usage:
    from app.config import settings
    print(settings.YOUTUBE_API_KEY)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All external API credentials required by Creator Content Radar."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    YOUTUBE_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "creator-content-radar/0.1"
    GEMINI_API_KEY: str = ""


# Singleton – import this everywhere
settings = Settings()
