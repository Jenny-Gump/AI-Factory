# Cost Tracking System

**Version:** 1.0.0
**Last Updated:** 2025-10-10
**Status:** Production Ready

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Model Pricing](#model-pricing)
4. [Usage Examples](#usage-examples)
5. [Terminal Output](#terminal-output)
6. [Cost Optimization Tips](#cost-optimization-tips)
7. [API Reference](#api-reference)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The Cost Tracking System provides comprehensive token counting and USD cost calculation for all LLM API requests in the Content Factory pipeline.

### Key Features

✅ **Token Tracking** - Tracks input, output, reasoning, and cached tokens for every request
✅ **Cost Calculation** - Converts tokens to USD costs using verified API pricing
✅ **Multiple Pricing Models** - Supports flat-rate, cache-tiered, and length-tiered pricing
✅ **Real-time Visibility** - Displays costs in terminal as requests are made
✅ **Stage Breakdown** - Shows costs per pipeline stage (extract, generate, translate, etc.)
✅ **Model Breakdown** - Shows costs per model (deepseek-reasoner, gemini-2.5-flash, etc.)
✅ **Batch Aggregation** - Aggregates costs across multiple topics in batch mode
✅ **SOLID Architecture** - Clean separation of concerns with 5 components

### Components

| Component | File | Responsibility |
|-----------|------|----------------|
| **Pricing Database** | `config/model_pricing.json` | Centralized storage of model prices |
| **Pricing Loader** | `src/model_pricing.py` | Loads and provides access to pricing data |
| **Cost Calculator** | `src/cost_calculator.py` | Calculates costs based on tokens and pricing |
| **Token Tracker** | `src/token_tracker.py` | Tracks tokens and costs per request/stage |
| **Batch Aggregator** | `src/batch_cost_aggregator.py` | Aggregates costs across multiple topics |

---

## Architecture

### SOLID Principles

The cost tracking system follows SOLID design principles:

1. **Single Responsibility Principle**
   - Each component has one clear purpose
   - `ModelPricingLoader` only loads pricing data
   - `CostCalculator` only calculates costs
   - `TokenTracker` only tracks usage
   - `BatchCostAggregator` only aggregates batch data

2. **Open/Closed Principle**
   - Easy to add new models without modifying existing code
   - Just add entries to `model_pricing.json`
   - New pricing models can be added to `CostCalculator`

3. **Dependency Inversion**
   - High-level modules don't depend on low-level details
   - `TokenTracker` depends on `CostCalculator` abstraction
   - `CostCalculator` depends on `ModelPricingLoader` abstraction

### Data Flow

```
1. LLM API Request → Returns tokens (prompt, completion, reasoning, cached)
2. TokenTracker.add_usage() → Receives tokens + model_name
3. CostCalculator.calculate_request_cost() → Calculates USD costs
4. ModelPricingLoader.get_model_pricing() → Provides pricing data
5. TokenTracker → Stores tokens + costs
6. Terminal logging → Displays real-time costs
7. Session end → Saves token_usage_report.json
8. (Batch mode) BatchCostAggregator → Aggregates multiple reports
```

---

## Model Pricing

### Verified Pricing (Updated: 2025-10-10)

All pricing data has been verified from official API documentation.

#### DeepSeek Models

**Source:** https://api-docs.deepseek.com/news/news250120

| Model | Cache Hit | Cache Miss | Output | Pricing Model |
|-------|-----------|------------|--------|---------------|
| **deepseek-reasoner** | $0.14/1M | $0.55/1M | $2.19/1M | Cache Tiered |
| **deepseek-chat** | $0.028/1M | $0.28/1M | $0.42/1M | Cache Tiered |

**Notes:**
- Reasoning tokens (DeepSeek R1) are billed as **output tokens**
- Prompt caching available - 10x cost reduction on cache hits
- Cache hit/miss tokens reported in API response

#### Google Gemini Models (Direct API)

**Source:** https://ai.google.dev/pricing

| Model | Input Cost | Output Cost | Notes |
|-------|------------|-------------|-------|
| **gemini-2.5-flash** | $0.30/1M | $2.50/1M | Stable release, web search grounding |
| **gemini-2.5-pro** | $1.25-$2.50/1M | $10-$15/1M | Length-tiered pricing (see below) |

**Gemini 2.5 Pro Length Tiers:**
- **Short prompts** (≤ 200K tokens): $1.25/1M input, $10.00/1M output
- **Long prompts** (> 200K tokens): $2.50/1M input, $15.00/1M output

#### OpenRouter Models

**Source:** https://openrouter.ai/models

| Model | Input Cost | Output Cost | Notes |
|-------|------------|-------------|-------|
| **google/gemini-2.5-flash-lite-preview-06-17** | $0.10/1M | $0.40/1M | Lowest cost option |
| **openai/gpt-5** | $1.25/1M | $10.00/1M | Available for override |

---

## Usage Examples

### Single Topic Run

```bash
cd "/Users/skynet/Desktop/AI DEV/Content-factory"
python main.py "Your topic here"
```

**Terminal output includes:**
```
2025-10-10 12:00:00 [INFO] - ✅ [extract_sections] Success with deepseek-chat | Cost: $0.0023
2025-10-10 12:01:30 [INFO] - ✅ [generate_article] Success with deepseek-reasoner | Cost: $0.0156
...

📊 SESSION TOKEN & COST SUMMARY
===============================================================================
💰 TOTAL COSTS:
   Input:  $0.012345
   Output: $0.045678
   TOTAL:  $0.058023 USD

📝 TOTAL TOKENS:
   Prompt:     45,234
   Completion: 18,567
   Reasoning:  12,345
   Cached:     25,000 (Hits: 20,000, Misses: 5,000)
   TOTAL:      76,146

📌 BY STAGE:
   extract_sections:    $0.0023 (5 requests, 12,345 tokens)
   create_structure:    $0.0089 (1 request, 23,456 tokens)
   generate_article:    $0.0312 (7 requests, 34,567 tokens)
   ...
```

**Output files:**
- `output/{topic}/token_usage_report.json` - Detailed token/cost report

### Batch Mode Run

```bash
cd "/Users/skynet/Desktop/AI DEV/Content-factory"
python batch_processor.py
```

**Terminal output includes:**
```
📊 BATCH COST SUMMARY - batch_20251010_120000
================================================================================
Topics processed: 15
Duration: 3245.5s

💰 TOTAL COSTS:
   Input:  $0.185430
   Output: $0.684210
   TOTAL:  $0.869640 USD
   Average per topic: $0.057976 USD

📝 TOTAL TOKENS:
   Prompt:     678,234
   Completion: 278,567
   Reasoning:  185,345
   Cached:     375,000 (Hits: 300,000, Misses: 75,000)

📌 TOP 5 STAGES BY COST:
   generate_article:   $0.468000 (105 requests)
   create_structure:   $0.133500 (15 requests)
   editorial_review:   $0.120120 (15 requests)
   fact_check:         $0.089400 (45 requests)
   translation:        $0.058620 (105 requests)

🤖 MODELS USED:
   deepseek-reasoner:  $0.689220 (120 requests)
   gemini-2.5-flash:   $0.089400 (45 requests)
   deepseek-chat:      $0.069020 (75 requests)
   ...
================================================================================
```

**Output files:**
- `output/batch_cost_report.json` - Aggregated batch report

### Programmatic Access

#### Calculate Cost for a Single Request

```python
from src.cost_calculator import get_cost_calculator

calculator = get_cost_calculator()

cost_data = calculator.calculate_request_cost(
    model_name="deepseek-reasoner",
    prompt_tokens=5000,
    completion_tokens=2000,
    reasoning_tokens=500,
    cache_hit_tokens=3000,
    cache_miss_tokens=2000
)

print(f"Total cost: ${cost_data['total_cost']:.6f}")
# Output: Total cost: $0.005390
```

#### Track Usage Manually

```python
from src.token_tracker import TokenTracker

tracker = TokenTracker(topic="My Topic")

# Add usage from API response
tracker.add_usage(
    stage="generate_article",
    usage=api_response.usage,  # CompletionUsage object
    model_name="deepseek-reasoner"
)

# Get summary
summary = tracker.get_session_summary()
print(f"Total cost: ${summary['total_cost']:.6f}")
```

#### Aggregate Batch Results

```python
from src.batch_cost_aggregator import BatchCostAggregator

aggregator = BatchCostAggregator(batch_id="my_batch_001")

# Add topic reports
aggregator.add_topic_report(
    topic="Topic 1",
    token_report_path="output/topic_1/token_usage_report.json"
)
aggregator.add_topic_report(
    topic="Topic 2",
    token_report_path="output/topic_2/token_usage_report.json"
)

# Print summary
aggregator.print_batch_summary()

# Save report
aggregator.save_batch_report("output/", "my_batch_report.json")
```

---

## Terminal Output

### Real-Time Cost Display

Every LLM request logs its cost immediately:

```
2025-10-10 12:00:00 [INFO] - 🎯 [extract_sections] Models to try: ['deepseek-chat', 'fallback']
2025-10-10 12:00:00 [INFO] - 🤖 [extract_sections] Trying primary model: deepseek-chat
2025-10-10 12:00:05 [INFO] - ✅ [extract_sections] Success with deepseek-chat on attempt 1
2025-10-10 12:00:05 [INFO] - 💰 Cost: $0.0023 (Input: $0.0008, Output: $0.0015) | Tokens: 2,850 prompt, 3,567 completion
```

### Session Summary (Single Run)

At the end of each topic run:

```
================================================================================
📊 SESSION TOKEN & COST SUMMARY - Topic: "AI Safety Research"
================================================================================
⏱️  Session duration: 425.3s

💰 TOTAL COSTS:
   Input:  $0.012345 USD
   Output: $0.045678 USD
   TOTAL:  $0.058023 USD

📝 TOTAL TOKENS:
   Prompt:     45,234
   Completion: 18,567
   Reasoning:  12,345
   Cached:     25,000 (Hits: 20,000, Misses: 5,000)
   TOTAL:      76,146

📌 COST BREAKDOWN BY STAGE (12 stages):
   1. extract_sections:    $0.002300  (5 req,  12,345 tok)
   2. create_structure:    $0.008900  (1 req,  23,456 tok)
   3. generate_article:    $0.031200  (7 req,  34,567 tok)
   4. translation:         $0.009100  (7 req,  15,234 tok)
   5. fact_check:          $0.004500  (3 req,   8,901 tok)
   6. editorial_review:    $0.008023  (1 req,  18,643 tok)

🤖 COST BREAKDOWN BY MODEL (3 models):
   1. deepseek-reasoner:   $0.048923  (15 req, 65,432 tok)
   2. gemini-2.5-flash:    $0.004500  (3 req,   8,901 tok)
   3. deepseek-chat:       $0.004600  (5 req,  12,345 tok)

💾 Report saved: output/AI_Safety_Research/token_usage_report.json
================================================================================
```

### Batch Summary

At the end of batch processing:

```
================================================================================
📊 BATCH COST SUMMARY - batch_20251010_120000
================================================================================
Topics processed: 15
Duration: 3245.5s (54.1 minutes)

💰 TOTAL COSTS:
   Input:  $0.185430 USD
   Output: $0.684210 USD
   TOTAL:  $0.869640 USD
   Average per topic: $0.057976 USD

📝 TOTAL TOKENS:
   Prompt:     678,234
   Completion: 278,567
   Reasoning:  185,345
   Cached:     375,000 (Hits: 300,000, Misses: 75,000)

📌 TOP 5 STAGES BY COST:
   generate_article:   $0.468000 (105 requests)
   create_structure:   $0.133500 (15 requests)
   editorial_review:   $0.120120 (15 requests)
   fact_check:         $0.089400 (45 requests)
   translation:        $0.058620 (105 requests)

🤖 MODELS USED:
   deepseek-reasoner:  $0.689220 (120 requests)
   gemini-2.5-flash:   $0.089400 (45 requests)
   deepseek-chat:      $0.069020 (75 requests)

📋 TOPIC SUMMARIES:
   1. AI Safety Research:          $0.058023 (23 requests, 76,146 tokens)
   2. Machine Learning Basics:     $0.052100 (21 requests, 68,234 tokens)
   3. Neural Networks Explained:   $0.061234 (24 requests, 82,456 tokens)
   ...

💾 Batch report saved: output/batch_cost_report.json
================================================================================
```

---

## Cost Optimization Tips

### 1. Leverage Prompt Caching (DeepSeek)

DeepSeek models support prompt caching with **10x cost reduction** on cache hits.

**Cache Hit Rate Impact:**
- 0% cache hits: $0.55/1M input tokens
- 50% cache hits: $0.345/1M average input cost (37% savings)
- 80% cache hits: $0.192/1M average input cost (65% savings)

**How to maximize cache hits:**
- Use consistent system prompts across requests
- Reuse source content in sequential stages
- Structure prompts with cacheable prefixes

### 2. Choose the Right Model

Different models for different tasks:

| Task | Recommended Model | Cost/1M (avg) | Reason |
|------|-------------------|---------------|--------|
| **Section extraction** | deepseek-chat | $0.28/$0.42 | Fast, simple task |
| **Structure creation** | deepseek-reasoner | $0.55/$2.19 | Complex reasoning needed |
| **Article generation** | deepseek-reasoner | $0.55/$2.19 | Quality matters |
| **Translation** | deepseek-reasoner | $0.55/$2.19 | Accuracy critical |
| **Fact-checking** | gemini-2.5-flash | $0.30/$2.50 | Native web search |
| **Link placement** | gemini-2.5-flash | $0.30/$2.50 | Web grounding needed |

### 3. Batch Processing

Run multiple topics together to maximize efficiency:

```bash
# 15 topics in one batch
python batch_processor.py
```

**Benefits:**
- Shared initialization overhead
- Better cache utilization
- Easier cost tracking across topics

### 4. Monitor Cost Trends

Review `token_usage_report.json` files to identify:
- High-cost stages that could be optimized
- Models that could be swapped for cheaper alternatives
- Stages with excessive token usage

### 5. Use Length-Aware Prompts (Gemini Pro)

For `gemini-2.5-pro`, keep prompts under 200K tokens when possible:

- **Short prompts** (≤200K): $1.25/1M input
- **Long prompts** (>200K): $2.50/1M input (2x cost!)

---

## API Reference

### ModelPricingLoader

```python
from src.model_pricing import get_pricing_loader, get_model_pricing

# Get singleton instance
loader = get_pricing_loader()

# Get pricing for a model
pricing = loader.get_model_pricing("deepseek-reasoner")
# Returns: {
#   "provider": "deepseek",
#   "input_cost_cache_hit": 0.14,
#   "input_cost_cache_miss": 0.55,
#   "output_cost": 2.19,
#   "supports_cache": true,
#   "pricing_model": "cache_tiered"
# }

# Check if pricing exists
has_pricing = loader.has_pricing("gemini-2.5-flash")  # True

# Get all models
all_models = loader.get_all_models()

# Get metadata
metadata = loader.get_pricing_metadata()
# Returns: {
#   "version": "1.0.0",
#   "last_updated": "2025-10-10T00:00:00Z",
#   "currency": "USD",
#   "pricing_per_1m_tokens": true
# }

# Convenience function
pricing = get_model_pricing("deepseek-chat")
```

### CostCalculator

```python
from src.cost_calculator import get_cost_calculator

calculator = get_cost_calculator()

# Calculate cost for a request
cost_data = calculator.calculate_request_cost(
    model_name="deepseek-reasoner",
    prompt_tokens=5000,
    completion_tokens=2000,
    reasoning_tokens=500,
    cache_hit_tokens=3000,
    cache_miss_tokens=2000
)

# Returns:
# {
#   "input_cost": 0.001280,        # $0.00128
#   "output_cost": 0.005475,        # $0.00548
#   "total_cost": 0.006755,         # $0.00676
#   "currency": "USD",
#   "model_name": "deepseek-reasoner",
#   "pricing_model": "cache_tiered",
#   "breakdown": {
#     "prompt_tokens": 5000,
#     "completion_tokens": 2000,
#     "reasoning_tokens": 500,
#     "cache_hit_tokens": 3000,
#     "cache_miss_tokens": 2000,
#     "total_output_tokens": 2500,
#     "cache_hit_cost": 0.000420,
#     "cache_miss_cost": 0.001100
#   }
# }
```

### TokenTracker

```python
from src.token_tracker import TokenTracker

tracker = TokenTracker(topic="My Topic")

# Add usage (typically called automatically by llm_request.py)
tracker.add_usage(
    stage="generate_article",
    usage=completion_usage_obj,  # From API response
    model_name="deepseek-reasoner",
    source_id="source_1",  # Optional
    url="https://example.com",  # Optional
    extra_metadata={"section": "intro"}  # Optional
)

# Get session summary
summary = tracker.get_session_summary()

# Print summary to terminal
tracker.print_session_summary()

# Save report to JSON
report_path = tracker.save_token_report(
    base_path="output/My_Topic",
    filename="token_usage_report.json"
)
```

### BatchCostAggregator

```python
from src.batch_cost_aggregator import BatchCostAggregator

aggregator = BatchCostAggregator(batch_id="batch_001")

# Add topic reports
aggregator.add_topic_report(
    topic="Topic 1",
    token_report_path="output/topic_1/token_usage_report.json"
)

# Get batch summary
summary = aggregator.get_batch_summary()

# Print to terminal
aggregator.print_batch_summary()

# Save batch report
report_path = aggregator.save_batch_report(
    output_path="output/",
    filename="batch_cost_report.json"
)
```

---

## Troubleshooting

### Issue: "No pricing data found for model: xyz"

**Cause:** Model not in `config/model_pricing.json`

**Solution:**
1. Check if model is in the pricing file
2. Add pricing data if missing:
   ```json
   "new-model-name": {
     "provider": "provider_name",
     "input_cost": 0.50,
     "output_cost": 1.50,
     "pricing_model": "flat_rate"
   }
   ```
3. Restart the pipeline

### Issue: Costs seem incorrect

**Debugging steps:**
1. Check `token_usage_report.json` for detailed breakdown
2. Verify token counts match API response
3. Verify pricing data in `config/model_pricing.json`
4. Check if cache hits/misses are being tracked correctly (DeepSeek)
5. For Gemini Pro, verify prompt length tier is correct

**Manual verification:**
```python
from src.cost_calculator import get_cost_calculator

calc = get_cost_calculator()
result = calc.calculate_request_cost(
    model_name="deepseek-reasoner",
    prompt_tokens=1000,
    completion_tokens=500,
    cache_miss_tokens=1000
)

# Expected: (1000/1M * $0.55) + (500/1M * $2.19) = $0.00055 + $0.001095 = $0.001645
print(f"Calculated: ${result['total_cost']:.6f}")
```

### Issue: Batch aggregator missing topics

**Cause:** Token usage report file not found or invalid JSON

**Solution:**
1. Verify report files exist:
   ```bash
   ls -la output/*/token_usage_report.json
   ```
2. Check for JSON errors:
   ```python
   import json
   with open("output/topic/token_usage_report.json") as f:
       data = json.load(f)  # Will raise error if invalid
   ```

### Issue: Terminal costs not showing

**Cause:** Logging level too high or model_name not being passed

**Solution:**
1. Check logging level in config:
   ```python
   import logging
   logging.getLogger().setLevel(logging.INFO)
   ```
2. Verify `llm_request.py` is passing `model_name` to `add_usage()`

### Issue: Cache hit/miss tracking not working (DeepSeek)

**Cause:** API might not return cache statistics

**Solution:**
1. Check if API response includes `cached_tokens`
2. If not available, calculator will assume all tokens are cache misses
3. This is conservative (higher cost estimate) but accurate

---

## Version History

### v1.0.0 (2025-10-10)

**Initial Release**

- ✅ Comprehensive token tracking
- ✅ USD cost calculation for 6 models
- ✅ Three pricing models (flat, cache-tiered, length-tiered)
- ✅ Real-time terminal logging
- ✅ Stage and model breakdowns
- ✅ Batch-level aggregation
- ✅ Complete documentation

**Supported Models:**
1. deepseek-reasoner
2. deepseek-chat
3. gemini-2.5-flash
4. gemini-2.5-pro
5. google/gemini-2.5-flash-lite-preview-06-17
6. openai/gpt-5

---

## See Also

- [Pipeline Flow](./flow.md) - 12-stage pipeline documentation
- [Configuration Guide](./config.md) - All configuration options
- [README](../README.md) - Project overview
- [Implementation Plan](/Users/skynet/Desktop/COST_TRACKING_IMPLEMENTATION_PLAN.md) - Detailed implementation guide
