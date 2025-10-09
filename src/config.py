import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Firecrawl API ---
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

# --- File Paths ---
BLOCKED_DOMAINS_PATH = "filters/blocked_domains.json"
TRUSTED_SOURCES_PATH = "filters/trusted_sources.json"

# --- Search Parameters ---
SEARCH_DOMAINS = [
    "*.ai",
    "*.io",
    "*.org",
    "*.edu",
    "*.com",
    "*.co",
    "*.net",
    "*.tech",
    "*.news",
    "*.media"
]

# --- Parsing Parameters ---
MIN_CONTENT_LENGTH = 10000  # Minimum number of characters for a valid article
CONCURRENT_REQUESTS = 5   # Number of concurrent requests to Firecrawl Scrape API

# --- Scoring Weights ---
TRUST_SCORE_WEIGHT = 0.5
RELEVANCE_SCORE_WEIGHT = 0.3
DEPTH_SCORE_WEIGHT = 0.2

# --- Selection ---
TOP_N_SOURCES = 5

# --- WordPress Publishing Configuration ---
WORDPRESS_API_URL = os.getenv("WORDPRESS_API_URL", "https://ailynx.ru/wp-json/wp/v2")
WORDPRESS_USERNAME = os.getenv("WORDPRESS_USERNAME", "PetrovA")
WORDPRESS_APP_PASSWORD = os.getenv("WORDPRESS_APP_PASSWORD")
USE_CUSTOM_META_ENDPOINT = os.getenv("USE_CUSTOM_META_ENDPOINT", "true").lower() == "true"
CUSTOM_POST_META_API_KEY = os.getenv("CUSTOM_POST_META_API_KEY", "")
WORDPRESS_CATEGORY = os.getenv("WORDPRESS_CATEGORY", "prompts")
WORDPRESS_STATUS = os.getenv("WORDPRESS_STATUS", "draft")


# --- LLM Models Configuration ---
# Models for different pipeline stages
LLM_MODELS = {
    "extract_sections": "deepseek-chat",                                # DeepSeek Chat for section extraction
    "create_structure": "deepseek-reasoner",                            # DeepSeek Reasoner for structure creation
    "generate_article": "deepseek-reasoner",                            # DeepSeek Reasoner for article generation
    "fact_check": "gemini-2.5-flash-preview-09-2025",                   # Google Gemini 2.5 Flash (Sept 2025) with native web search for fact-checking
    "link_placement": "gemini-2.5-flash-preview-09-2025",               # Google Gemini 2.5 Flash (Sept 2025) with native web search for finding relevant links
    "translation": "deepseek-reasoner",                                 # DeepSeek Reasoner for translation
    "editorial_review": "deepseek-reasoner",                            # DeepSeek Reasoner for editorial review
}

# Fallback models for each stage (used when primary model fails)
FALLBACK_MODELS = {
    "extract_sections": "google/gemini-2.5-flash-lite-preview-06-17",    # Fallback to Gemini 2.5
    "create_structure": "google/gemini-2.5-flash-lite-preview-06-17",   # Fallback to Gemini 2.5
    "generate_article": "google/gemini-2.5-flash-lite-preview-06-17",   # Fallback to Gemini 2.5
    "fact_check": "gemini-2.5-flash",                                   # Stable Gemini 2.5 Flash with web search
    "link_placement": "gemini-2.5-flash",                               # Stable Gemini 2.5 Flash with web search
    "translation": "google/gemini-2.5-flash-lite-preview-06-17",        # Fallback to Gemini 2.5
    "editorial_review": "google/gemini-2.5-flash-lite-preview-06-17",   # Fallback to Gemini 2.5
}

# Retry configuration for LLM requests
RETRY_CONFIG = {
    "max_attempts": 3,
    "delays": [2, 5, 10],  # seconds between retries
    "use_fallback_on_final_failure": True
}

# Section generation timeout configuration
SECTION_TIMEOUT = 180  # 3 minutes total timeout per section
MODEL_TIMEOUT = 60     # 1 minute timeout per model (primary + fallback)
SECTION_MAX_RETRIES = 3  # Maximum retries per section

# Default model if no specific model is configured
DEFAULT_MODEL = "deepseek-reasoner"

# --- LLM Providers Configuration ---
LLM_PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models": [
            "deepseek-reasoner",
            "deepseek-chat"
        ]
    },
    "google_direct": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key_env": "GEMINI_API_KEY",
        "models": [
            "gemini-2.5-flash-preview-09-2025",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash"
        ],
        "supports_web_search": True
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "models": [
            "openai/gpt-5",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/gpt-4-turbo",
            "openai/gpt-3.5-turbo",
            "google/gemini-2.0-flash-001",
            "google/gemini-2.5-flash-lite-preview-06-17",
            "google/gemini-2.0-flash-exp:free",
            "deepseek/deepseek-chat-v3.1:free",
            "perplexity/sonar-reasoning-pro",
            "perplexity/sonar-reasoning-pro:online",
            "x-ai/grok-4-fast:free",
            "z-ai/glm-4.5-air:free"
        ],
        "extra_headers": {
            "HTTP-Referer": "https://github.com/your-repo/content-generator",
            "X-Title": "AI Content Generator"
        },
        "provider_preferences": {
            "order": ["DeepInfra"],
            "allow_fallbacks": False
        }
    }
}

# Model to provider mapping
def get_provider_for_model(model_name: str) -> str:
    """Get the provider name for a given model."""
    for provider, config in LLM_PROVIDERS.items():
        if model_name in config["models"]:
            return provider
    # Default to deepseek for unknown models
    return "deepseek"
