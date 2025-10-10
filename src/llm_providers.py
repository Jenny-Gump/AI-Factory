"""
LLM Provider routing and abstraction layer

This module provides a unified interface for routing LLM requests to different providers:
- OpenRouter (for DeepSeek free, Google free models, etc.)
- DeepSeek Direct (for deepseek-reasoner, deepseek-chat)
- Google Direct (for Gemini models with native web search)

Follows SOLID principles:
- Single Responsibility: Each class handles one provider
- Open/Closed: Easy to add new providers
- Liskov Substitution: All providers return consistent format
- Interface Segregation: Minimal provider interface
- Dependency Inversion: Depends on abstractions
"""
import os
import requests
import logging
from typing import Dict, List, Optional, Tuple, Any
from types import SimpleNamespace
from openai import OpenAI

from src.config import LLM_PROVIDERS, get_provider_for_model

# Lazy logger initialization - will use config from configure_logging()
logger = logging.getLogger(__name__)


class LLMProviderRouter:
    """
    Routes LLM requests to appropriate providers and handles API calls.

    This is the main entry point for all LLM API calls. It:
    - Determines which provider to use based on model name
    - Initializes and caches API clients
    - Routes requests to appropriate provider implementations
    - Returns responses in unified format
    """

    def __init__(self):
        """Initialize provider router with empty client cache"""
        self._clients_cache: Dict[str, OpenAI] = {}

    def route_request(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        enable_web_search: bool = False
    ) -> Tuple[Any, str]:
        """
        Route request to appropriate provider and make API call.

        Args:
            model_name: Name of the LLM model (e.g., "deepseek/deepseek-chat-v3.1:free")
            messages: List of chat messages in OpenAI format
            temperature: Model temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            response_format: Response format specification (e.g., {"type": "json_object"})
            enable_web_search: Enable web search for supported models (Google only)

        Returns:
            Tuple[response_object, provider_name]

        Raises:
            ValueError: If provider is unknown or API key is missing
            Exception: If API call fails
        """
        provider = get_provider_for_model(model_name)

        logger.info(f"🔀 Routing model '{model_name}' to provider: {provider}")

        if provider == "google_direct":
            return self._call_google_direct(
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_web_search=enable_web_search
            )
        elif provider == "deepseek":
            return self._call_deepseek_direct(
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format
            )
        elif provider == "openrouter":
            return self._call_openrouter(
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format
            )
        else:
            raise ValueError(f"Unknown provider '{provider}' for model '{model_name}'")

    def _get_or_create_client(self, provider: str) -> OpenAI:
        """
        Get cached OpenAI client or create new one for provider.

        Args:
            provider: Provider name (e.g., "openrouter", "deepseek")

        Returns:
            OpenAI client instance

        Raises:
            ValueError: If API key not found in environment
        """
        # Return cached client if available
        if provider in self._clients_cache:
            logger.debug(f"Using cached client for provider: {provider}")
            return self._clients_cache[provider]

        # Get provider configuration
        provider_config = LLM_PROVIDERS.get(provider)
        if not provider_config:
            raise ValueError(f"Provider '{provider}' not found in LLM_PROVIDERS config")

        # Get API key from environment
        api_key = os.getenv(provider_config["api_key_env"])
        if not api_key:
            raise ValueError(
                f"API key not found for provider '{provider}'. "
                f"Check {provider_config['api_key_env']} in .env file"
            )

        # Create client with provider-specific configuration
        client_kwargs = {
            "api_key": api_key,
            "base_url": provider_config["base_url"]
        }

        # Add extra headers for OpenRouter
        if "extra_headers" in provider_config:
            client_kwargs["default_headers"] = provider_config["extra_headers"]
            logger.debug(f"Added extra headers for {provider}: {list(provider_config['extra_headers'].keys())}")

        # Create and cache client
        client = OpenAI(**client_kwargs)
        self._clients_cache[provider] = client

        logger.info(f"✅ Created new client for provider: {provider}")
        return client

    def _call_openrouter(
        self,
        model_name: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int],
        response_format: Optional[Dict]
    ) -> Tuple[Any, str]:
        """
        Call OpenRouter API.

        OpenRouter supports:
        - Google Gemini models (google/gemini-2.5-flash-lite-preview-06-17)
        - Various free and paid models with unified API

        Args:
            model_name: Model identifier
            messages: Chat messages
            temperature: Model temperature
            max_tokens: Max tokens
            response_format: Response format (optional)

        Returns:
            Tuple[response_object, provider_name]
        """
        client = self._get_or_create_client("openrouter")

        # Build API call kwargs
        kwargs = {
            "temperature": temperature
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if response_format:
            kwargs["response_format"] = response_format

        # Apply provider preferences ONLY for DeepSeek models
        if "deepseek" in model_name.lower():
            provider_config = LLM_PROVIDERS.get("openrouter", {})
            provider_prefs = provider_config.get("provider_preferences")
            if provider_prefs:
                kwargs["extra_body"] = {"provider": provider_prefs}
                logger.info(f"🔧 Applying provider preferences for {model_name}: {provider_prefs}")

        logger.debug(f"🔧 OpenRouter API call kwargs: {list(kwargs.keys())}")

        # Make API call
        response_obj = client.chat.completions.create(
            model=model_name,
            messages=messages,
            **kwargs
        )

        return response_obj, "openrouter"

    def _call_deepseek_direct(
        self,
        model_name: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int],
        response_format: Optional[Dict]
    ) -> Tuple[Any, str]:
        """
        Call DeepSeek Direct API.

        Used for:
        - deepseek-reasoner (R1 reasoning model)
        - deepseek-chat (standard chat model)

        Supports JSON mode via response_format.

        Args:
            model_name: Model identifier (e.g., "deepseek-reasoner")
            messages: Chat messages
            temperature: Model temperature
            max_tokens: Max tokens
            response_format: Response format (optional, for JSON mode)

        Returns:
            Tuple[response_object, provider_name]
        """
        client = self._get_or_create_client("deepseek")

        # Build API call kwargs
        kwargs = {
            "temperature": temperature
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if response_format:
            kwargs["response_format"] = response_format
            logger.info(f"🔧 DeepSeek API using response_format: {response_format}")

        # Make API call
        response_obj = client.chat.completions.create(
            model=model_name,
            messages=messages,
            **kwargs
        )

        return response_obj, "deepseek"

    def _call_google_direct(
        self,
        model_name: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int],
        enable_web_search: bool
    ) -> Tuple[Any, str]:
        """
        Call Google Gemini API directly via HTTP.

        Google Direct API features:
        - Native web search (grounding) support
        - Higher rate limits than OpenRouter
        - Converts OpenAI message format to Google's contents format

        Args:
            model_name: Gemini model name (e.g., "gemini-2.5-flash")
            messages: Chat messages in OpenAI format
            temperature: Model temperature
            max_tokens: Max tokens (up to 65536 for Gemini 2.5 Flash)
            enable_web_search: Enable Google Search grounding

        Returns:
            Tuple[response_object, provider_name]

        Raises:
            ValueError: If GEMINI_API_KEY not found
            Exception: If API call fails
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        headers = {
            "Content-Type": "application/json"
        }

        # Convert OpenAI messages format to Google contents format
        system_content = ""
        user_content = ""

        for message in messages:
            if message["role"] == "system":
                system_content = message["content"]
            elif message["role"] == "user":
                user_content = message["content"]

        # Combine system and user content for Google format
        combined_content = f"{system_content}\n\n{user_content}" if system_content else user_content

        # Build Google API request
        request_data = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": combined_content
                        }
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens or 65536,  # Maximum for Gemini 2.5 Flash
                "temperature": temperature,
                "topP": 0.8,
                "topK": 40
            }
        }

        # Add web search tools if requested
        logger.info(f"🔧 _call_google_direct: enable_web_search={enable_web_search}, model={model_name}")
        if enable_web_search:
            request_data["tools"] = [
                {
                    "google_search": {}
                }
            ]
            logger.info(f"🔍 Enabled Google Search grounding for {model_name}")
        else:
            logger.warning(f"⚠️ Web search NOT enabled for {model_name}")

        # Make HTTP request
        response = requests.post(url, headers=headers, json=request_data, timeout=120)

        if response.status_code != 200:
            raise Exception(f"Google API error: HTTP {response.status_code} - {response.text}")

        result = response.json()

        logger.debug(f"🔍 Google API response size: {len(response.text)} chars")

        # Extract content from response
        if "candidates" not in result or not result["candidates"]:
            raise Exception("No candidates in Google API response")

        candidate = result["candidates"][0]

        if "content" not in candidate:
            raise Exception("No content in Google API response")

        # Gemini can return multiple parts, combine them
        parts = candidate["content"]["parts"]
        logger.debug(f"🔍 Gemini returned {len(parts)} part(s)")

        # Combine all text parts
        content_parts = []
        for idx, part in enumerate(parts):
            if "text" in part:
                part_text = part["text"]
                content_parts.append(part_text)
                logger.debug(f"   Part {idx+1}: {len(part_text)} chars")
            else:
                logger.warning(f"⚠️ Part {idx+1} has no 'text' field: {list(part.keys())}")

        content = "".join(content_parts)
        logger.info(f"📏 Google API total content: {len(content)} chars")

        # Create OpenAI-compatible response object
        response_obj = SimpleNamespace()
        response_obj.choices = [SimpleNamespace()]
        response_obj.choices[0].message = SimpleNamespace()
        response_obj.choices[0].message.content = content
        response_obj.choices[0].finish_reason = candidate.get("finishReason", "stop")

        # Add usage information if available
        if "usageMetadata" in result:
            usage_metadata = result["usageMetadata"]
            response_obj.usage = SimpleNamespace()
            response_obj.usage.prompt_tokens = usage_metadata.get("promptTokenCount", 0)
            response_obj.usage.completion_tokens = usage_metadata.get("candidatesTokenCount", 0)
            response_obj.usage.total_tokens = usage_metadata.get("totalTokenCount", 0)
        else:
            # No usage info available
            response_obj.usage = None

        # Extract grounding metadata if available (web search results)
        if "groundingMetadata" in candidate:
            grounding_metadata = candidate["groundingMetadata"]
            response_obj.grounding_metadata = grounding_metadata

            # Log grounding information
            web_queries = grounding_metadata.get("webSearchQueries", [])
            grounding_chunks = grounding_metadata.get("groundingChunks", [])
            logger.info(f"🔍 Web Search Queries: {len(web_queries)} query(ies)")
            logger.info(f"📚 Grounding Chunks: {len(grounding_chunks)} source(s)")

            if web_queries:
                logger.debug(f"   Queries: {web_queries}")
        else:
            response_obj.grounding_metadata = None

        return response_obj, "google_direct"


# Global singleton instance
_provider_router = LLMProviderRouter()


def get_provider_router() -> LLMProviderRouter:
    """
    Get the global LLMProviderRouter instance.

    Returns:
        LLMProviderRouter singleton
    """
    return _provider_router
