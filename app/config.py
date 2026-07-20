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
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    AI_PROVIDER: str = "auto"  # auto, gemini, groq, openrouter


# Singleton – import this everywhere
settings = Settings()
