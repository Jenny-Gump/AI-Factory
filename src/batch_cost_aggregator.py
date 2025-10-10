"""
Batch Cost Aggregator

Single Responsibility: Aggregate costs and token usage across multiple topics in batch mode.
Collects token usage reports from individual runs and provides batch-level summaries.

Architecture: Stateful aggregator that collects data from multiple topic runs.
"""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BatchCostAggregator:
    """
    Aggregates cost and token data across multiple topics in a batch run.

    Collects individual token usage reports and provides:
    - Total costs across all topics
    - Per-stage cost breakdowns
    - Per-model usage statistics
    - Individual topic summaries
    """

    def __init__(self, batch_id: Optional[str] = None):
        """
        Initialize the batch cost aggregator.

        Args:
            batch_id: Optional batch identifier (auto-generated if not provided)
        """
        self.batch_id = batch_id or f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.topics: List[str] = []
        self.topic_reports: Dict[str, Dict] = {}
        self.start_time = datetime.now()

    def add_topic_report(self, topic: str, token_report_path: str) -> None:
        """
        Add a token usage report from a completed topic run.

        Args:
            topic: The topic name
            token_report_path: Path to the token_usage_report.json file

        Raises:
            FileNotFoundError: If report file doesn't exist
            json.JSONDecodeError: If report file is invalid JSON
        """
        if not os.path.exists(token_report_path):
            logger.error(f"❌ Token report not found for topic '{topic}': {token_report_path}")
            raise FileNotFoundError(f"Token report not found: {token_report_path}")

        try:
            with open(token_report_path, 'r', encoding='utf-8') as f:
                report_data = json.load(f)

            self.topics.append(topic)
            self.topic_reports[topic] = report_data

            # Log addition
            total_cost = report_data.get('session_summary', {}).get('total_cost', 0.0)
            logger.info(f"✅ Added topic '{topic}' to batch | Cost: ${total_cost:.4f}")

        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in token report for '{topic}': {e}")
            raise

    def get_batch_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive summary of the entire batch run.

        Returns:
            Dict with batch-level aggregations including:
            - Total costs (input, output, total)
            - Total tokens (prompt, completion, reasoning, cached)
            - Per-stage aggregations
            - Per-model aggregations
            - Individual topic summaries
        """
        if not self.topics:
            logger.warning("⚠️ No topics added to batch aggregator")
            return self._empty_summary()

        # Initialize aggregation containers
        total_costs = {"input": 0.0, "output": 0.0, "total": 0.0}
        total_tokens = {
            "prompt": 0,
            "completion": 0,
            "reasoning": 0,
            "cached": 0,
            "cache_hit": 0,
            "cache_miss": 0
        }
        stage_aggregations = {}
        model_aggregations = {}
        topic_summaries = []

        # Aggregate data from all topics
        for topic, report in self.topic_reports.items():
            session_summary = report.get('session_summary', {})

            # Aggregate costs
            total_costs["input"] += session_summary.get('total_input_cost', 0.0)
            total_costs["output"] += session_summary.get('total_output_cost', 0.0)
            total_costs["total"] += session_summary.get('total_cost', 0.0)

            # Aggregate tokens
            total_tokens["prompt"] += session_summary.get('total_prompt_tokens', 0)
            total_tokens["completion"] += session_summary.get('total_completion_tokens', 0)
            total_tokens["reasoning"] += session_summary.get('total_reasoning_tokens', 0)
            total_tokens["cached"] += session_summary.get('total_cached_tokens', 0)
            total_tokens["cache_hit"] += session_summary.get('total_cache_hit_tokens', 0)
            total_tokens["cache_miss"] += session_summary.get('total_cache_miss_tokens', 0)

            # Aggregate by stage
            for stage_data in report.get('by_stage', []):
                stage = stage_data.get('stage', 'unknown')
                if stage not in stage_aggregations:
                    stage_aggregations[stage] = {
                        "total_cost": 0.0,
                        "total_tokens": 0,
                        "request_count": 0
                    }

                stage_aggregations[stage]["total_cost"] += stage_data.get('total_cost', 0.0)
                stage_aggregations[stage]["total_tokens"] += stage_data.get('total_tokens', 0)
                stage_aggregations[stage]["request_count"] += stage_data.get('request_count', 0)

            # Aggregate by model
            for model_data in report.get('by_model', []):
                model = model_data.get('model_name', 'unknown')
                if model not in model_aggregations:
                    model_aggregations[model] = {
                        "total_cost": 0.0,
                        "total_tokens": 0,
                        "request_count": 0
                    }

                model_aggregations[model]["total_cost"] += model_data.get('total_cost', 0.0)
                model_aggregations[model]["total_tokens"] += model_data.get('total_tokens', 0)
                model_aggregations[model]["request_count"] += model_data.get('request_count', 0)

            # Topic summary
            topic_summaries.append({
                "topic": topic,
                "total_cost": session_summary.get('total_cost', 0.0),
                "total_tokens": session_summary.get('total_tokens', 0),
                "request_count": session_summary.get('request_count', 0),
                "stages": len(report.get('by_stage', []))
            })

        # Convert aggregations to sorted lists
        by_stage = [
            {"stage": stage, **data}
            for stage, data in sorted(stage_aggregations.items())
        ]

        by_model = [
            {"model_name": model, **data}
            for model, data in sorted(
                model_aggregations.items(),
                key=lambda x: x[1]["total_cost"],
                reverse=True
            )
        ]

        # Build summary
        end_time = datetime.now()
        duration_seconds = (end_time - self.start_time).total_seconds()

        return {
            "batch_id": self.batch_id,
            "total_topics": len(self.topics),
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": round(duration_seconds, 2),
            "currency": "USD",
            "total_costs": {
                "input_cost": round(total_costs["input"], 6),
                "output_cost": round(total_costs["output"], 6),
                "total_cost": round(total_costs["total"], 6)
            },
            "total_tokens": total_tokens,
            "by_stage": by_stage,
            "by_model": by_model,
            "topics": topic_summaries,
            "average_cost_per_topic": round(total_costs["total"] / len(self.topics), 6) if self.topics else 0.0
        }

    def save_batch_report(
        self,
        output_path: str,
        filename: str = "batch_cost_report.json"
    ) -> str:
        """
        Save the batch cost report to a JSON file.

        Args:
            output_path: Directory to save the report
            filename: Name of the report file

        Returns:
            Path to the saved report file
        """
        os.makedirs(output_path, exist_ok=True)
        report_path = os.path.join(output_path, filename)

        summary = self.get_batch_summary()

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Batch cost report saved: {report_path}")
        return report_path

    def print_batch_summary(self) -> None:
        """
        Print a formatted batch summary to the console.
        """
        summary = self.get_batch_summary()

        print("\n" + "=" * 80)
        print(f"📊 BATCH COST SUMMARY - {summary['batch_id']}")
        print("=" * 80)
        print(f"Topics processed: {summary['total_topics']}")
        print(f"Duration: {summary['duration_seconds']:.1f}s")
        print()
        print(f"💰 TOTAL COSTS:")
        print(f"   Input:  ${summary['total_costs']['input_cost']:.6f}")
        print(f"   Output: ${summary['total_costs']['output_cost']:.6f}")
        print(f"   TOTAL:  ${summary['total_costs']['total_cost']:.6f}")
        print(f"   Average per topic: ${summary['average_cost_per_topic']:.6f}")
        print()
        print(f"📝 TOTAL TOKENS:")
        print(f"   Prompt:     {summary['total_tokens']['prompt']:,}")
        print(f"   Completion: {summary['total_tokens']['completion']:,}")
        print(f"   Reasoning:  {summary['total_tokens']['reasoning']:,}")
        if summary['total_tokens']['cached'] > 0:
            print(f"   Cached:     {summary['total_tokens']['cached']:,} "
                  f"(Hits: {summary['total_tokens']['cache_hit']:,}, "
                  f"Misses: {summary['total_tokens']['cache_miss']:,})")
        print()
        print(f"📌 TOP 5 STAGES BY COST:")
        for stage_data in sorted(summary['by_stage'], key=lambda x: x['total_cost'], reverse=True)[:5]:
            print(f"   {stage_data['stage']}: ${stage_data['total_cost']:.6f} "
                  f"({stage_data['request_count']} requests)")
        print()
        print(f"🤖 MODELS USED:")
        for model_data in summary['by_model']:
            print(f"   {model_data['model_name']}: ${model_data['total_cost']:.6f} "
                  f"({model_data['request_count']} requests)")
        print("=" * 80 + "\n")

    def _empty_summary(self) -> Dict[str, Any]:
        """
        Return an empty summary when no topics have been added.
        """
        return {
            "batch_id": self.batch_id,
            "total_topics": 0,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration_seconds": 0.0,
            "currency": "USD",
            "total_costs": {
                "input_cost": 0.0,
                "output_cost": 0.0,
                "total_cost": 0.0
            },
            "total_tokens": {
                "prompt": 0,
                "completion": 0,
                "reasoning": 0,
                "cached": 0,
                "cache_hit": 0,
                "cache_miss": 0
            },
            "by_stage": [],
            "by_model": [],
            "topics": [],
            "average_cost_per_topic": 0.0
        }
