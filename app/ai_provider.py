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


def select_provider(
    complexity: ComplexityLevel = ComplexityLevel.MEDIUM,
    preferred_provider: AIProvider | None = None,
) -> AIProvider:
    """Select the best AI provider based on complexity and availability.
    
    Args:
        complexity: The complexity level of the task
        preferred_provider: Optional preferred provider override
        
    Returns:
        Selected AI provider
        
    Raises:
        ValueError: If no providers are available
    """
    available = get_available_providers()
    
    if not available:
        raise ValueError("No AI providers available. Please configure at least one API key.")
    
    # If specific provider is requested and available, use it
    if preferred_provider and preferred_provider in available:
        logger.info(f"Using preferred provider: {preferred_provider.value}")
        return preferred_provider
    
    # If AI_PROVIDER is set to a specific provider, use it
    if settings.AI_PROVIDER != "auto":
        try:
            requested = AIProvider(settings.AI_PROVIDER)
            if requested in available:
                logger.info(f"Using configured provider: {requested.value}")
                return requested
        except ValueError:
            logger.warning(f"Invalid AI_PROVIDER setting: {settings.AI_PROVIDER}, using auto-selection")
    
    # Auto-selection based on complexity and provider preferences
    for provider in available:
        provider_prefs = PROVIDER_INFO[provider]["complexity_preference"]
        if complexity in provider_prefs:
            logger.info(f"Auto-selected provider {provider.value} for complexity {complexity.value}")
            return provider
    
    # Fallback to first available provider
    logger.warning(f"No provider preference match for complexity {complexity.value}, using fallback")
    return available[0]


def get_provider_client(provider: AIProvider):
    """Get the appropriate client for the selected provider.
    
    Args:
        provider: The AI provider to get a client for
        
    Returns:
        Configured client for the provider
    """
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
    
    Args:
        prompt: The prompt to send to the AI
        complexity: Complexity level of the task
        preferred_provider: Optional preferred provider
        **kwargs: Additional provider-specific arguments
        
    Returns:
        AI-generated response text
        
    Raises:
        ValueError: If all providers fail
    """
    available = get_available_providers()
    
    if not available:
        raise ValueError("No AI providers available. Please configure at least one API key.")
    
    # Try providers in order of preference
    tried_providers = []
    
    for provider in available:
        try:
            selected = select_provider(complexity, preferred_provider)
            if selected not in tried_providers:
                tried_providers.append(selected)
                
                logger.info(f"Attempting provider: {selected.value}")
                client = get_provider_client(selected)
                response = _call_provider(client, selected, prompt, **kwargs)
                
                logger.info(f"Successfully generated response using {selected.value}")
                return response
                
        except Exception as exc:
            logger.warning(f"Provider {selected.value if selected in tried_providers else provider.value} failed: {exc}")
            continue
    
    raise ValueError(f"All AI providers failed. Tried: {[p.value for p in tried_providers]}")


def _call_provider(client, provider: AIProvider, prompt: str, **kwargs) -> str:
    """Call the specific provider with the prompt.
    
    Args:
        client: The provider client
        provider: The AI provider
        prompt: The prompt to send
        **kwargs: Additional arguments
        
    Returns:
        Provider response text
    """
    if provider == AIProvider.GEMINI:
        model = kwargs.get("model", "gemini-2.0-flash")
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text
    
    elif provider == AIProvider.GROQ:
        model = kwargs.get("model", "llama-3.3-70b-versatile")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.7),
        )
        return response.choices[0].message.content
    
    elif provider == AIProvider.OPENROUTER:
        model = kwargs.get("model", "anthropic/claude-3.5-sonnet")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.7),
        )
        return response.choices[0].message.content
    
    else:
        raise ValueError(f"Unknown provider: {provider}")
