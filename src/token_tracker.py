"""
Token usage tracking module for LLM requests in Content Generator.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from openai.types.completion_usage import CompletionUsage

from src.logger_config import logger


class TokenTracker:
    """
    Tracks token usage across all LLM requests in a pipeline session.
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
    
    def add_usage(self, 
                  stage: str, 
                  usage: CompletionUsage,
                  source_id: Optional[str] = None,
                  url: Optional[str] = None,
                  extra_metadata: Optional[Dict] = None) -> None:
        """
        Record token usage from an LLM request.
        
        Args:
            stage: Pipeline stage (e.g., "extract_prompts", "generate_article")
            usage: CompletionUsage object from OpenAI response
            source_id: Optional source identifier (e.g., "source_1")
            url: Optional source URL
            extra_metadata: Additional metadata to store
        """
        try:
            # Extract token information from usage object
            token_entry = {
                "timestamp": datetime.now().isoformat(),
                "stage": stage,
                "source_id": source_id,
                "url": url[:100] + "..." if url and len(url) > 100 else url,
                
                # Core token counts
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                
                # DeepSeek-specific tokens
                "reasoning_tokens": getattr(usage.completion_tokens_details, 'reasoning_tokens', None) 
                                  if usage.completion_tokens_details else None,
                
                # Cache information
                "cached_tokens": getattr(usage.prompt_tokens_details, 'cached_tokens', 0) 
                               if usage.prompt_tokens_details else 0,
                "cache_hit_tokens": getattr(usage, 'prompt_cache_hit_tokens', 0),
                "cache_miss_tokens": getattr(usage, 'prompt_cache_miss_tokens', 0),
                
                # Additional metadata
                "metadata": extra_metadata or {}
            }
            
            self.session_tokens.append(token_entry)
            
            # Log token usage in real-time
            reasoning_info = f", Reasoning: {token_entry['reasoning_tokens']}" if token_entry['reasoning_tokens'] else ""
            logger.info(f"Token usage [{stage}] - "
                       f"Prompt: {usage.prompt_tokens}, "
                       f"Completion: {usage.completion_tokens}, "
                       f"Total: {usage.total_tokens}"
                       f"{reasoning_info}")
            
        except Exception as e:
            logger.error(f"Failed to record token usage: {e}")
    
    def get_session_summary(self) -> Dict[str, Any]:
        """
        Generate summary statistics for the current session.
        
        Returns:
            Dictionary with session totals and breakdown
        """
        if not self.session_tokens:
            return {
                "session_summary": {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "total_reasoning_tokens": 0,
                    "total_cached_tokens": 0,
                    "total_requests": 0,
                    "topic": self.topic,
                    "session_start": self.session_start.isoformat(),
                    "session_duration_minutes": 0
                },
                "detailed_breakdown": []
            }
        
        # Calculate totals
        total_prompt = sum(entry["prompt_tokens"] for entry in self.session_tokens)
        total_completion = sum(entry["completion_tokens"] for entry in self.session_tokens)
        total_tokens = sum(entry["total_tokens"] for entry in self.session_tokens)
        total_reasoning = sum(entry["reasoning_tokens"] or 0 for entry in self.session_tokens)
        total_cached = sum(entry["cached_tokens"] for entry in self.session_tokens)
        total_requests = len(self.session_tokens)
        
        # Calculate session duration
        session_end = datetime.now()
        duration_minutes = round((session_end - self.session_start).total_seconds() / 60, 2)
        
        # Group by stage for breakdown
        stage_breakdown = {}
        for entry in self.session_tokens:
            stage = entry["stage"]
            if stage not in stage_breakdown:
                stage_breakdown[stage] = {
                    "requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "reasoning_tokens": 0
                }
            
            stage_breakdown[stage]["requests"] += 1
            stage_breakdown[stage]["prompt_tokens"] += entry["prompt_tokens"]
            stage_breakdown[stage]["completion_tokens"] += entry["completion_tokens"]
            stage_breakdown[stage]["total_tokens"] += entry["total_tokens"]
            stage_breakdown[stage]["reasoning_tokens"] += entry["reasoning_tokens"] or 0
        
        return {
            "session_summary": {
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_tokens": total_tokens,
                "total_reasoning_tokens": total_reasoning,
                "total_cached_tokens": total_cached,
                "total_requests": total_requests,
                "topic": self.topic,
                "session_start": self.session_start.isoformat(),
                "session_end": session_end.isoformat(),
                "session_duration_minutes": duration_minutes,
                "average_tokens_per_request": round(total_tokens / total_requests, 1) if total_requests > 0 else 0
            },
            "stage_breakdown": stage_breakdown,
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
            
            # Log summary statistics
            session_summary = summary["session_summary"]
            logger.info(f"💰 SESSION TOKEN SUMMARY:")
            logger.info(f"   📊 Total requests: {session_summary['total_requests']}")
            logger.info(f"   📥 Total prompt tokens: {session_summary['total_prompt_tokens']:,}")
            logger.info(f"   📤 Total completion tokens: {session_summary['total_completion_tokens']:,}")
            logger.info(f"   🔢 Total tokens: {session_summary['total_tokens']:,}")
            if session_summary['total_reasoning_tokens'] > 0:
                logger.info(f"   🧠 Total reasoning tokens: {session_summary['total_reasoning_tokens']:,}")
            logger.info(f"   ⏱️  Session duration: {session_summary['session_duration_minutes']} minutes")
            logger.info(f"   📄 Token report saved: {report_path}")
            
            return report_path
            
        except Exception as e:
            logger.error(f"Failed to save token report: {e}")
            return ""
    
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
        stage_requests = len(stage_entries)
        
        logger.info(f"🎯 Stage '{stage}' summary: {stage_total:,} tokens ({stage_requests} requests)")