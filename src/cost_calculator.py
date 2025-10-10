"""
Cost Calculator

Single Responsibility: Calculate USD costs based on tokens and pricing data.
Takes token counts and model name, retrieves pricing, and calculates costs.

Architecture: Standalone calculator that uses ModelPricingLoader for data.
"""

from typing import Dict, Optional
import logging
from src.model_pricing import get_pricing_loader

logger = logging.getLogger(__name__)


class CostCalculator:
    """
    Calculates USD costs for LLM API requests based on token counts and pricing data.

    Supports three pricing models:
    1. flat_rate: Simple input/output pricing
    2. cache_tiered: DeepSeek models with cache hit/miss pricing
    3. length_tiered: Gemini Pro with short/long prompt pricing
    """

    def __init__(self):
        """Initialize the cost calculator."""
        self.pricing_loader = get_pricing_loader()
        self.metadata = self.pricing_loader.get_pricing_metadata()
        self.currency = self.metadata.get('currency', 'USD')
        self.per_1m_tokens = self.metadata.get('pricing_per_1m_tokens', True)

    def calculate_request_cost(
        self,
        model_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_tokens: int = 0,
        cache_hit_tokens: int = 0,
        cache_miss_tokens: int = 0
    ) -> Dict[str, float]:
        """
        Calculate the cost of an LLM API request.

        Args:
            model_name: Name of the model used
            prompt_tokens: Number of input/prompt tokens
            completion_tokens: Number of output/completion tokens
            reasoning_tokens: Number of reasoning tokens (DeepSeek R1)
            cached_tokens: Total cached tokens (DeepSeek - may be split into hit/miss)
            cache_hit_tokens: Tokens served from cache (DeepSeek)
            cache_miss_tokens: Tokens not in cache (DeepSeek)

        Returns:
            Dict with cost breakdown:
            {
                "input_cost": 0.0012,
                "output_cost": 0.0045,
                "total_cost": 0.0057,
                "currency": "USD",
                "model_name": "deepseek-reasoner",
                "pricing_model": "cache_tiered",
                "breakdown": {
                    "prompt_tokens": 5000,
                    "completion_tokens": 2000,
                    "reasoning_tokens": 500,
                    "cache_hit_tokens": 3000,
                    "cache_miss_tokens": 2000
                }
            }

        Note:
            - For DeepSeek models: reasoning_tokens are billed as output tokens
            - If cache_hit_tokens/cache_miss_tokens not provided, falls back to prompt_tokens
            - All costs are per 1M tokens (divide by 1,000,000)
        """
        # Get pricing data for model
        pricing = self.pricing_loader.get_model_pricing(model_name)

        if not pricing:
            logger.warning(f"⚠️ No pricing data for {model_name}, returning zero cost")
            return self._zero_cost_result(model_name, prompt_tokens, completion_tokens,
                                         reasoning_tokens, cached_tokens)

        pricing_model = pricing.get('pricing_model', 'flat_rate')

        # Calculate based on pricing model
        if pricing_model == 'cache_tiered':
            return self._calculate_cache_tiered(
                model_name, pricing, prompt_tokens, completion_tokens,
                reasoning_tokens, cache_hit_tokens, cache_miss_tokens
            )
        elif pricing_model == 'length_tiered':
            return self._calculate_length_tiered(
                model_name, pricing, prompt_tokens, completion_tokens
            )
        else:  # flat_rate
            return self._calculate_flat_rate(
                model_name, pricing, prompt_tokens, completion_tokens, reasoning_tokens
            )

    def _calculate_flat_rate(
        self,
        model_name: str,
        pricing: Dict,
        prompt_tokens: int,
        completion_tokens: int,
        reasoning_tokens: int = 0
    ) -> Dict[str, float]:
        """
        Calculate cost for flat-rate pricing models (Gemini Flash, GPT-5, etc.).

        Flat rate: Simple input_cost * input_tokens + output_cost * output_tokens
        """
        input_cost_per_1m = pricing.get('input_cost', 0.0)
        output_cost_per_1m = pricing.get('output_cost', 0.0)

        # For flat rate, reasoning tokens are billed as output tokens
        total_output_tokens = completion_tokens + reasoning_tokens

        # Calculate costs (prices are per 1M tokens)
        input_cost = (prompt_tokens / 1_000_000) * input_cost_per_1m
        output_cost = (total_output_tokens / 1_000_000) * output_cost_per_1m
        total_cost = input_cost + output_cost

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6),
            "currency": self.currency,
            "model_name": model_name,
            "pricing_model": "flat_rate",
            "breakdown": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "total_output_tokens": total_output_tokens
            }
        }

    def _calculate_cache_tiered(
        self,
        model_name: str,
        pricing: Dict,
        prompt_tokens: int,
        completion_tokens: int,
        reasoning_tokens: int,
        cache_hit_tokens: int,
        cache_miss_tokens: int
    ) -> Dict[str, float]:
        """
        Calculate cost for cache-tiered pricing (DeepSeek models).

        Cache tiers:
        - cache_hit_tokens: Cheaper rate (served from cache)
        - cache_miss_tokens: Standard rate (not in cache)
        - reasoning_tokens: Billed as output tokens (DeepSeek R1)

        If cache_hit/miss not provided, assumes all prompt_tokens are cache misses.
        """
        cache_hit_cost_per_1m = pricing.get('input_cost_cache_hit', 0.0)
        cache_miss_cost_per_1m = pricing.get('input_cost_cache_miss', 0.0)
        output_cost_per_1m = pricing.get('output_cost', 0.0)

        # If cache breakdown not provided, assume all prompts are cache misses
        if cache_hit_tokens == 0 and cache_miss_tokens == 0:
            cache_miss_tokens = prompt_tokens
            logger.debug(f"No cache breakdown for {model_name}, assuming {prompt_tokens} cache misses")

        # Calculate input cost (cache hits + cache misses)
        cache_hit_cost = (cache_hit_tokens / 1_000_000) * cache_hit_cost_per_1m
        cache_miss_cost = (cache_miss_tokens / 1_000_000) * cache_miss_cost_per_1m
        input_cost = cache_hit_cost + cache_miss_cost

        # Calculate output cost (completion + reasoning tokens)
        total_output_tokens = completion_tokens + reasoning_tokens
        output_cost = (total_output_tokens / 1_000_000) * output_cost_per_1m

        total_cost = input_cost + output_cost

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6),
            "currency": self.currency,
            "model_name": model_name,
            "pricing_model": "cache_tiered",
            "breakdown": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "cache_hit_tokens": cache_hit_tokens,
                "cache_miss_tokens": cache_miss_tokens,
                "total_output_tokens": total_output_tokens,
                "cache_hit_cost": round(cache_hit_cost, 6),
                "cache_miss_cost": round(cache_miss_cost, 6)
            }
        }

    def _calculate_length_tiered(
        self,
        model_name: str,
        pricing: Dict,
        prompt_tokens: int,
        completion_tokens: int
    ) -> Dict[str, float]:
        """
        Calculate cost for length-tiered pricing (Gemini Pro).

        Length tiers:
        - Short prompts (≤ threshold): Lower input/output costs
        - Long prompts (> threshold): Higher output costs, mid-tier input costs

        Threshold is typically 200K tokens for Gemini 2.5 Pro.
        """
        threshold = pricing.get('prompt_length_threshold', 200_000)

        # Determine which tier to use based on prompt length
        if prompt_tokens <= threshold:
            input_cost_per_1m = pricing.get('input_cost_short', 0.0)
            output_cost_per_1m = pricing.get('output_cost_short', 0.0)
            tier = "short"
        else:
            input_cost_per_1m = pricing.get('input_cost_long', 0.0)
            output_cost_per_1m = pricing.get('output_cost_long', 0.0)
            tier = "long"

        # Calculate costs
        input_cost = (prompt_tokens / 1_000_000) * input_cost_per_1m
        output_cost = (completion_tokens / 1_000_000) * output_cost_per_1m
        total_cost = input_cost + output_cost

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6),
            "currency": self.currency,
            "model_name": model_name,
            "pricing_model": "length_tiered",
            "tier": tier,
            "breakdown": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "threshold": threshold,
                "tier_used": tier
            }
        }

    def _zero_cost_result(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        reasoning_tokens: int,
        cached_tokens: int
    ) -> Dict[str, float]:
        """
        Return zero-cost result when pricing data is unavailable.
        """
        return {
            "input_cost": 0.0,
            "output_cost": 0.0,
            "total_cost": 0.0,
            "currency": self.currency,
            "model_name": model_name,
            "pricing_model": "unknown",
            "error": "No pricing data available for this model",
            "breakdown": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "cached_tokens": cached_tokens
            }
        }


# Singleton instance
_cost_calculator_instance: Optional[CostCalculator] = None


def get_cost_calculator() -> CostCalculator:
    """
    Get the singleton instance of CostCalculator.

    Returns:
        CostCalculator instance
    """
    global _cost_calculator_instance

    if _cost_calculator_instance is None:
        _cost_calculator_instance = CostCalculator()

    return _cost_calculator_instance
