"""AI Provider Manager — Handles multiple AI providers with fallback and complexity-based selection.

Supports Gemini, Groq, and OpenRouter with automatic fallback and complexity-based routing.
"""

import logging
from typing import Literal
from enum import Enum

from app.config import settings

logger = logging.getLogger(__name__)


class ComplexityLevel(Enum):
    """Complexity levels for AI tasks."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AIProvider(Enum):
    """Available AI providers."""
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"


# Provider capabilities and characteristics
PROVIDER_INFO = {
    AIProvider.GEMINI: {
        "name": "Google Gemini",
        "complexity_preference": [ComplexityLevel.HIGH, ComplexityLevel.MEDIUM, ComplexityLevel.LOW],
        "speed": "medium",
        "cost": "free_tier",
        "quality": "high",
    },
    AIProvider.GROQ: {
        "name": "Groq",
        "complexity_preference": [ComplexityLevel.LOW, ComplexityLevel.MEDIUM],
        "speed": "fast",
        "cost": "free",
        "quality": "medium",
    },
    AIProvider.OPENROUTER: {
        "name": "OpenRouter",
        "complexity_preference": [ComplexityLevel.HIGH, ComplexityLevel.MEDIUM, ComplexityLevel.LOW],
        "speed": "variable",
        "cost": "paid",
        "quality": "high",
    },
}

# Default models per provider
DEFAULT_MODELS = {
    AIProvider.GEMINI: "gemini-2.0-flash",
    AIProvider.GROQ: "llama-3.3-70b-versatile",
    AIProvider.OPENROUTER: "meta-llama/llama-3.3-70b-instruct",
}


def get_available_providers() -> list[AIProvider]:
    """Return list of available AI providers based on API keys."""
    available = []

    if settings.GEMINI_API_KEY:
        available.append(AIProvider.GEMINI)
    if settings.GROQ_API_KEY:
        available.append(AIProvider.GROQ)
    if settings.OPENROUTER_API_KEY:
        available.append(AIProvider.OPENROUTER)

    return available


def get_ordered_providers(complexity: ComplexityLevel) -> list[AIProvider]:
    """Return available providers ordered by preference for the given complexity.

    The first provider that matches the complexity level comes first, then
    the rest in availability order. This ensures we always try the best match
    first but fall through to all others.
    """
    available = get_available_providers()
    if not available:
        return []

    # If AI_PROVIDER is set to a specific provider, try it first
    if settings.AI_PROVIDER != "auto":
        try:
            requested = AIProvider(settings.AI_PROVIDER)
            if requested in available:
                # Move requested to front, keep rest in order
                available.remove(requested)
                available.insert(0, requested)
        except ValueError:
            logger.warning(f"Invalid AI_PROVIDER setting: {settings.AI_PROVIDER}")

    # For HIGH complexity, prefer Gemini/OpenRouter over Groq
    # For LOW complexity, prefer Groq first
    if complexity == ComplexityLevel.LOW:
        # Sort: Groq first, then others
        available.sort(key=lambda p: 0 if p == AIProvider.GROQ else 1)
    elif complexity == ComplexityLevel.HIGH:
        # Sort: OpenRouter/Gemini first, Groq last
        available.sort(key=lambda p: 1 if p == AIProvider.GROQ else 0)

    return available


def get_provider_client(provider: AIProvider):
    """Get the appropriate client for the selected provider."""
    if provider == AIProvider.GEMINI:
        from google import genai
        return genai.Client(api_key=settings.GEMINI_API_KEY)

    elif provider == AIProvider.GROQ:
        from groq import Groq
        return Groq(api_key=settings.GROQ_API_KEY)

    elif provider == AIProvider.OPENROUTER:
        from openai import OpenAI
        return OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )

    else:
        raise ValueError(f"Unknown provider: {provider}")


def generate_ai_response(
    prompt: str,
    complexity: ComplexityLevel = ComplexityLevel.MEDIUM,
    preferred_provider: AIProvider | None = None,
    **kwargs
) -> str:
    """Generate AI response using the best available provider with fallback.

    Tries providers in order of preference. If one fails (quota, auth, etc.),
    it falls through to the next available provider automatically.
    """
    available = get_available_providers()

    if not available:
        raise ValueError("No AI providers available. Please configure at least one API key.")

    # Build ordered list of providers to try
    if preferred_provider and preferred_provider in available:
        ordered = [preferred_provider] + [p for p in get_ordered_providers(complexity) if p != preferred_provider]
    else:
        ordered = get_ordered_providers(complexity)

    if not ordered:
        ordered = available

    errors = []

    for provider in ordered:
        try:
            logger.info(f"Attempting provider: {provider.value}")
            client = get_provider_client(provider)
            response = _call_provider(client, provider, prompt, **kwargs)

            logger.info(f"Successfully generated response using {provider.value}")
            return response

        except Exception as exc:
            error_msg = str(exc)[:200]
            logger.warning(f"Provider {provider.value} failed: {error_msg}")
            errors.append(f"{provider.value}: {error_msg}")
            continue

    raise ValueError(f"All AI providers failed. Tried: {errors}")


def _call_provider(client, provider: AIProvider, prompt: str, **kwargs) -> str:
    """Call the specific provider with the prompt."""
    model = kwargs.get("model", DEFAULT_MODELS[provider])

    if provider == AIProvider.GEMINI:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text

    elif provider == AIProvider.GROQ:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.7),
        )
        return response.choices[0].message.content

    elif provider == AIProvider.OPENROUTER:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.7),
        )
        return response.choices[0].message.content

    else:
        raise ValueError(f"Unknown provider: {provider}")
