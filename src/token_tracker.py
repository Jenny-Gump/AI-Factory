"""
Token usage tracking module for LLM requests in Content Generator.
Tracks both tokens and USD costs for all LLM requests.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from openai.types.completion_usage import CompletionUsage

from src.logger_config import logger
from src.cost_calculator import get_cost_calculator


class TokenTracker:
    """
    Tracks token usage and USD costs across all LLM requests in a pipeline session.
    """

    def __init__(self, topic: str = ""):
        """
        Initialize token tracker for a pipeline session.

        Args:
            topic: The topic being processed in this session
        """
        self.topic = topic
        self.session_tokens: List[Dict[str, Any]] = []
        self.session_start = datetime.now()
        self.cost_calculator = get_cost_calculator()

    def reset(self):
        """
        Reset token tracker for memory cleanup between topics.
        """
        self.session_tokens.clear()
        self.session_start = datetime.now()
        logger.info(f"Token tracker reset for topic: {self.topic}")
    
    def add_usage(self,
                  stage: str,
                  usage: CompletionUsage,
                  model_name: str = "unknown",
                  source_id: Optional[str] = None,
                  url: Optional[str] = None,
                  extra_metadata: Optional[Dict] = None) -> None:
        """
        Record token usage and cost from an LLM request.

        Args:
            stage: Pipeline stage (e.g., "extract_sections", "generate_article")
            usage: CompletionUsage object from OpenAI response
            model_name: Name of the model used (e.g., "deepseek-reasoner")
            source_id: Optional source identifier (e.g., "source_1")
            url: Optional source URL
            extra_metadata: Additional metadata to store
        """
        try:
            # Extract token information from usage object
            reasoning_tokens = getattr(usage.completion_tokens_details, 'reasoning_tokens', 0) \
                             if usage.completion_tokens_details else 0
            cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0) \
                          if usage.prompt_tokens_details else 0
            cache_hit_tokens = getattr(usage, 'prompt_cache_hit_tokens', 0)
            cache_miss_tokens = getattr(usage, 'prompt_cache_miss_tokens', 0)

            # Calculate cost for this request
            cost_data = self.cost_calculator.calculate_request_cost(
                model_name=model_name,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                reasoning_tokens=reasoning_tokens,
                cached_tokens=cached_tokens,
                cache_hit_tokens=cache_hit_tokens,
                cache_miss_tokens=cache_miss_tokens
            )

            token_entry = {
                "timestamp": datetime.now().isoformat(),
                "stage": stage,
                "model_name": model_name,
                "source_id": source_id,
                "url": url[:100] + "..." if url and len(url) > 100 else url,

                # Core token counts
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,

                # DeepSeek-specific tokens
                "reasoning_tokens": reasoning_tokens if reasoning_tokens else None,

                # Cache information
                "cached_tokens": cached_tokens,
                "cache_hit_tokens": cache_hit_tokens,
                "cache_miss_tokens": cache_miss_tokens,

                # Cost information (USD)
                "input_cost": cost_data.get('input_cost', 0.0),
                "output_cost": cost_data.get('output_cost', 0.0),
                "total_cost": cost_data.get('total_cost', 0.0),
                "currency": cost_data.get('currency', 'USD'),
                "pricing_model": cost_data.get('pricing_model', 'unknown'),

                # Additional metadata
                "metadata": extra_metadata or {}
            }
            
            self.session_tokens.append(token_entry)

            # Log token usage and cost in real-time
            reasoning_info = f", Reasoning: {token_entry['reasoning_tokens']}" if token_entry['reasoning_tokens'] else ""
            cost_info = f" | 💰 Cost: ${token_entry['total_cost']:.6f} (Input: ${token_entry['input_cost']:.6f}, Output: ${token_entry['output_cost']:.6f})"

            logger.info(f"Token usage [{stage}] [{model_name}] - "
                       f"Prompt: {usage.prompt_tokens:,}, "
                       f"Completion: {usage.completion_tokens:,}, "
                       f"Total: {usage.total_tokens:,}"
                       f"{reasoning_info}"
                       f"{cost_info}")
            
        except Exception as e:
            logger.error(f"Failed to record token usage: {e}")
    
    def get_session_summary(self) -> Dict[str, Any]:
        """
        Generate summary statistics for the current session including costs.

        Returns:
            Dictionary with session totals, cost breakdowns, and detailed breakdown
        """
        if not self.session_tokens:
            return {
                "session_summary": {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "total_reasoning_tokens": 0,
                    "total_cached_tokens": 0,
                    "total_cache_hit_tokens": 0,
                    "total_cache_miss_tokens": 0,
                    "total_input_cost": 0.0,
                    "total_output_cost": 0.0,
                    "total_cost": 0.0,
                    "currency": "USD",
                    "request_count": 0,
                    "topic": self.topic,
                    "session_start": self.session_start.isoformat(),
                    "session_duration_minutes": 0
                },
                "by_stage": [],
                "by_model": [],
                "detailed_breakdown": []
            }
        
        # Calculate totals
        total_prompt = sum(entry["prompt_tokens"] for entry in self.session_tokens)
        total_completion = sum(entry["completion_tokens"] for entry in self.session_tokens)
        total_tokens = sum(entry["total_tokens"] for entry in self.session_tokens)
        total_reasoning = sum(entry["reasoning_tokens"] or 0 for entry in self.session_tokens)
        total_cached = sum(entry["cached_tokens"] for entry in self.session_tokens)
        total_cache_hit = sum(entry["cache_hit_tokens"] for entry in self.session_tokens)
        total_cache_miss = sum(entry["cache_miss_tokens"] for entry in self.session_tokens)
        total_requests = len(self.session_tokens)

        # Calculate cost totals
        total_input_cost = sum(entry["input_cost"] for entry in self.session_tokens)
        total_output_cost = sum(entry["output_cost"] for entry in self.session_tokens)
        total_cost = sum(entry["total_cost"] for entry in self.session_tokens)

        # Calculate session duration
        session_end = datetime.now()
        duration_minutes = round((session_end - self.session_start).total_seconds() / 60, 2)

        # Group by stage for breakdown
        stage_breakdown = {}
        for entry in self.session_tokens:
            stage = entry["stage"]
            if stage not in stage_breakdown:
                stage_breakdown[stage] = {
                    "request_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "reasoning_tokens": 0,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "total_cost": 0.0
                }

            stage_breakdown[stage]["request_count"] += 1
            stage_breakdown[stage]["prompt_tokens"] += entry["prompt_tokens"]
            stage_breakdown[stage]["completion_tokens"] += entry["completion_tokens"]
            stage_breakdown[stage]["total_tokens"] += entry["total_tokens"]
            stage_breakdown[stage]["reasoning_tokens"] += entry["reasoning_tokens"] or 0
            stage_breakdown[stage]["input_cost"] += entry["input_cost"]
            stage_breakdown[stage]["output_cost"] += entry["output_cost"]
            stage_breakdown[stage]["total_cost"] += entry["total_cost"]

        # Group by model for breakdown
        model_breakdown = {}
        for entry in self.session_tokens:
            model = entry["model_name"]
            if model not in model_breakdown:
                model_breakdown[model] = {
                    "request_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "reasoning_tokens": 0,
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "total_cost": 0.0
                }

            model_breakdown[model]["request_count"] += 1
            model_breakdown[model]["prompt_tokens"] += entry["prompt_tokens"]
            model_breakdown[model]["completion_tokens"] += entry["completion_tokens"]
            model_breakdown[model]["total_tokens"] += entry["total_tokens"]
            model_breakdown[model]["reasoning_tokens"] += entry["reasoning_tokens"] or 0
            model_breakdown[model]["input_cost"] += entry["input_cost"]
            model_breakdown[model]["output_cost"] += entry["output_cost"]
            model_breakdown[model]["total_cost"] += entry["total_cost"]
        
        # Convert breakdowns to sorted lists
        by_stage = [
            {"stage": stage, **data}
            for stage, data in sorted(stage_breakdown.items())
        ]

        by_model = [
            {"model_name": model, **data}
            for model, data in sorted(
                model_breakdown.items(),
                key=lambda x: x[1]["total_cost"],
                reverse=True
            )
        ]

        return {
            "session_summary": {
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_tokens": total_tokens,
                "total_reasoning_tokens": total_reasoning,
                "total_cached_tokens": total_cached,
                "total_cache_hit_tokens": total_cache_hit,
                "total_cache_miss_tokens": total_cache_miss,
                "total_input_cost": round(total_input_cost, 6),
                "total_output_cost": round(total_output_cost, 6),
                "total_cost": round(total_cost, 6),
                "currency": "USD",
                "request_count": total_requests,
                "topic": self.topic,
                "session_start": self.session_start.isoformat(),
                "session_end": session_end.isoformat(),
                "session_duration_minutes": duration_minutes,
                "average_tokens_per_request": round(total_tokens / total_requests, 1) if total_requests > 0 else 0,
                "average_cost_per_request": round(total_cost / total_requests, 6) if total_requests > 0 else 0.0
            },
            "by_stage": by_stage,
            "by_model": by_model,
            "detailed_breakdown": self.session_tokens
        }
    
    def save_token_report(self, base_path: str, filename: str = "token_usage_report.json") -> str:
        """
        Save detailed token usage report to file.
        
        Args:
            base_path: Directory to save the report
            filename: Name of the report file
            
        Returns:
            Path to saved report file
        """
        try:
            os.makedirs(base_path, exist_ok=True)
            report_path = os.path.join(base_path, filename)
            
            summary = self.get_session_summary()
            
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            # Print detailed summary to terminal
            self.print_session_summary(summary)
            
            return report_path
            
        except Exception as e:
            logger.error(f"Failed to save token report: {e}")
            return ""
    
    def print_session_summary(self, summary: Optional[Dict[str, Any]] = None) -> None:
        """
        Print a detailed session summary with costs to the terminal.

        Args:
            summary: Optional pre-computed summary dict. If None, will compute it.
        """
        if summary is None:
            summary = self.get_session_summary()

        session_summary = summary["session_summary"]
        by_stage = summary.get("by_stage", [])
        by_model = summary.get("by_model", [])

        # Print separator
        logger.info("=" * 80)
        logger.info(f"📊 SESSION TOKEN & COST SUMMARY - Topic: {session_summary.get('topic', 'Unknown')}")
        logger.info("=" * 80)
        logger.info(f"⏱️  Session duration: {session_summary['session_duration_minutes']} minutes")
        logger.info("")

        # Print total costs
        logger.info("💰 TOTAL COSTS:")
        logger.info(f"   Input:  ${session_summary['total_input_cost']:.6f} {session_summary['currency']}")
        logger.info(f"   Output: ${session_summary['total_output_cost']:.6f} {session_summary['currency']}")
        logger.info(f"   TOTAL:  ${session_summary['total_cost']:.6f} {session_summary['currency']}")
        logger.info("")

        # Print total tokens
        logger.info("📝 TOTAL TOKENS:")
        logger.info(f"   Prompt:     {session_summary['total_prompt_tokens']:,}")
        logger.info(f"   Completion: {session_summary['total_completion_tokens']:,}")
        if session_summary['total_reasoning_tokens'] > 0:
            logger.info(f"   Reasoning:  {session_summary['total_reasoning_tokens']:,}")
        if session_summary['total_cached_tokens'] > 0:
            logger.info(f"   Cached:     {session_summary['total_cached_tokens']:,} "
                       f"(Hits: {session_summary['total_cache_hit_tokens']:,}, "
                       f"Misses: {session_summary['total_cache_miss_tokens']:,})")
        logger.info(f"   TOTAL:      {session_summary['total_tokens']:,}")
        logger.info("")

        # Print breakdown by stage
        if by_stage:
            logger.info(f"📌 COST BREAKDOWN BY STAGE ({len(by_stage)} stages):")
            for stage_data in by_stage:
                logger.info(f"   {stage_data['stage']:25s} ${stage_data['total_cost']:8.6f}  "
                           f"({stage_data['request_count']:2d} req, {stage_data['total_tokens']:7,} tok)")
            logger.info("")

        # Print breakdown by model
        if by_model:
            logger.info(f"🤖 COST BREAKDOWN BY MODEL ({len(by_model)} models):")
            for model_data in by_model:
                logger.info(f"   {model_data['model_name']:45s} ${model_data['total_cost']:8.6f}  "
                           f"({model_data['request_count']:3d} req, {model_data['total_tokens']:8,} tok)")
            logger.info("")

        logger.info(f"💾 Report saved: {os.path.basename(self.topic)}/token_usage_report.json")
        logger.info("=" * 80 + "\n")

    def log_stage_summary(self, stage: str) -> None:
        """
        Log summary for a specific stage.

        Args:
            stage: The stage to summarize
        """
        stage_entries = [entry for entry in self.session_tokens if entry["stage"] == stage]
        if not stage_entries:
            return

        stage_total = sum(entry["total_tokens"] for entry in stage_entries)
        stage_cost = sum(entry["total_cost"] for entry in stage_entries)
        stage_requests = len(stage_entries)

        logger.info(f"🎯 Stage '{stage}' summary: {stage_total:,} tokens, ${stage_cost:.6f} ({stage_requests} requests)")