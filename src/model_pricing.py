"""
Model Pricing Loader

Single Responsibility: Load and provide access to model pricing data.
Loads pricing information from config/model_pricing.json and provides
a clean interface to retrieve pricing for specific models.

Architecture: Singleton pattern for global access to pricing data.
"""

import json
import os
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ModelPricingLoader:
    """
    Loads and provides access to model pricing data.

    Follows Single Responsibility Principle - only handles loading
    and accessing pricing data, not calculating costs.
    """

    def __init__(self, pricing_file: str = "config/model_pricing.json"):
        """
        Initialize the pricing loader.

        Args:
            pricing_file: Path to the pricing JSON file relative to project root
        """
        self.pricing_file = pricing_file
        self.pricing_data: Dict = {}
        self._load_pricing_data()

    def _load_pricing_data(self) -> None:
        """
        Load pricing data from JSON file.

        Raises:
            FileNotFoundError: If pricing file doesn't exist
            json.JSONDecodeError: If pricing file is invalid JSON
        """
        # Get project root (parent of src/)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        pricing_path = os.path.join(project_root, self.pricing_file)

        if not os.path.exists(pricing_path):
            error_msg = f"Pricing file not found: {pricing_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        try:
            with open(pricing_path, 'r', encoding='utf-8') as f:
                self.pricing_data = json.load(f)

            logger.info(
                f"✅ Loaded pricing data v{self.pricing_data.get('pricing_version', 'unknown')} "
                f"with {len(self.pricing_data.get('models', {}))} models"
            )
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in pricing file: {e}"
            logger.error(error_msg)
            raise

    def get_model_pricing(self, model_name: str) -> Optional[Dict]:
        """
        Get pricing data for a specific model.

        Args:
            model_name: Name of the model (e.g., "deepseek-reasoner", "gemini-2.5-flash")

        Returns:
            Dict with pricing data or None if model not found.

        Example return for deepseek-reasoner:
        {
            "provider": "deepseek",
            "input_cost_cache_hit": 0.14,
            "input_cost_cache_miss": 0.55,
            "output_cost": 2.19,
            "supports_cache": true,
            "pricing_model": "cache_tiered"
        }
        """
        models = self.pricing_data.get('models', {})
        pricing = models.get(model_name)

        if pricing is None:
            logger.warning(f"⚠️ No pricing data found for model: {model_name}")

        return pricing

    def has_pricing(self, model_name: str) -> bool:
        """
        Check if pricing data exists for a model.

        Args:
            model_name: Name of the model

        Returns:
            True if pricing data exists, False otherwise
        """
        return model_name in self.pricing_data.get('models', {})

    def get_all_models(self) -> Dict[str, Dict]:
        """
        Get pricing data for all models.

        Returns:
            Dict mapping model names to their pricing data
        """
        return self.pricing_data.get('models', {})

    def get_pricing_metadata(self) -> Dict:
        """
        Get pricing metadata (version, currency, update date, etc.).

        Returns:
            Dict with pricing metadata
        """
        return {
            'version': self.pricing_data.get('pricing_version'),
            'last_updated': self.pricing_data.get('last_updated'),
            'currency': self.pricing_data.get('currency', 'USD'),
            'pricing_per_1m_tokens': self.pricing_data.get('pricing_per_1m_tokens', True),
            'sources': self.pricing_data.get('sources', {})
        }


# Singleton instance
_pricing_loader_instance: Optional[ModelPricingLoader] = None


def get_pricing_loader() -> ModelPricingLoader:
    """
    Get the singleton instance of ModelPricingLoader.

    This ensures we only load the pricing data once per session.

    Returns:
        ModelPricingLoader instance
    """
    global _pricing_loader_instance

    if _pricing_loader_instance is None:
        _pricing_loader_instance = ModelPricingLoader()

    return _pricing_loader_instance


# Convenience function for quick pricing lookup
def get_model_pricing(model_name: str) -> Optional[Dict]:
    """
    Quick lookup function for model pricing.

    Args:
        model_name: Name of the model

    Returns:
        Pricing data dict or None if not found
    """
    return get_pricing_loader().get_model_pricing(model_name)
