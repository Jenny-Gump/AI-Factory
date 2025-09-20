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

# --- Link Processing Configuration ---
LINK_PROCESSING_ENABLED = True  # Enable/disable link processing stage
LINK_MAX_QUERIES = 15  # Maximum number of search queries per article
LINK_MAX_CANDIDATES_PER_QUERY = 5  # Maximum candidates to fetch per query
LINK_PROCESSING_TIMEOUT = 360  # Maximum time in seconds for link processing (6 minutes)
LINK_SEARCH_TIMEOUT = 6  # Timeout per search request in seconds
LINK_HEAD_CHECK_TIMEOUT = 2  # Timeout for HEAD requests in seconds
LINK_MAX_CONCURRENT = 5  # Maximum concurrent search requests
LINK_MIN_SUCCESS_RATE = 0.7  # Minimum success rate for link resolution (70%)

# --- LLM Models Configuration ---
# Models for different pipeline stages
LLM_MODELS = {
    "extract_prompts": "deepseek/deepseek-chat-v3.1:free",              # FREE Model for prompt extraction from articles
    "create_structure": "deepseek/deepseek-chat-v3.1:free",             # FREE Model for creating ultimate structure (basic_articles)
    "generate_article": "deepseek/deepseek-chat-v3.1:free",             # FREE Model for WordPress article generation
    "editorial_review": "deepseek/deepseek-chat-v3.1:free",             # FREE Model for editorial review and cleanup
    "link_planning": "deepseek/deepseek-chat-v3.1:free",                # FREE Model for link planning
    "link_selection": "deepseek/deepseek-chat-v3.1:free",               # FREE Model for link selection from candidates
}

# Fallback models for each stage (used when primary model fails)
FALLBACK_MODELS = {
    "extract_prompts": "google/gemini-2.5-flash-lite-preview-06-17",    # Fallback to Gemini 2.5
    "create_structure": "google/gemini-2.5-flash-lite-preview-06-17",   # Fallback to Gemini 2.5
    "generate_article": "google/gemini-2.5-flash-lite-preview-06-17",   # Fallback to Gemini 2.5
    "editorial_review": "google/gemini-2.5-flash-lite-preview-06-17",   # Fallback to Gemini 2.5
    "link_planning": "google/gemini-2.5-flash-lite-preview-06-17",      # Fallback to Gemini 2.5
    "link_selection": "google/gemini-2.5-flash-lite-preview-06-17",     # Fallback to Gemini 2.5
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
DEFAULT_MODEL = "deepseek/deepseek-chat-v3.1:free"

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
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY", 
        "models": [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/gpt-4-turbo",
            "openai/gpt-3.5-turbo",
            "google/gemini-2.0-flash-001",
            "google/gemini-2.5-flash-lite-preview-06-17",
            "deepseek/deepseek-chat-v3.1:free"
        ],
        "extra_headers": {
            "HTTP-Referer": "https://github.com/your-repo/content-generator",
            "X-Title": "AI Content Generator"
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
