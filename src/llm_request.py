"""
Unified LLM Request Handler with Retry, Fallback, and Validation

This module provides a single entry point for all LLM API calls with automatic:
- Retry (3 attempts per model with progressive backoff)
- Fallback (primary → fallback model)
- Validation (v3.0, minimal, none, or custom)
- Provider routing (DeepSeek, Google, OpenRouter)
- Token tracking
- Response saving (for debugging)

Follows SOLID principles:
- Single Responsibility: Handles LLM requests only
- Open/Closed: Easy to extend with new validation levels
- Liskov Substitution: All providers return consistent format
- Interface Segregation: Clean minimal API
- Dependency Inversion: Depends on abstractions (provider router, validator)

Usage:
    from src.llm_request import make_llm_request

    response, model = make_llm_request(
        stage_name="generate_article",
        messages=[{"role": "user", "content": "Write about AI"}],
        temperature=0.3,
        validation_level="v3"
    )
"""
import os
import time
import json
from typing import Dict, List, Optional, Tuple, Callable, Any
from datetime import datetime

import logging

from src.config import LLM_MODELS, FALLBACK_MODELS, RETRY_CONFIG
from src.llm_providers import get_provider_router
from src.llm_validation import LLMResponseValidator
from src.token_tracker import TokenTracker

# Lazy logger initialization - will use config from configure_logging()
logger = logging.getLogger(__name__)


class LLMRequestHandler:
    """
    Handles all LLM requests with unified retry/fallback/validation logic.

    This is the main request handler that orchestrates:
    - Model selection (primary/fallback)
    - Retry logic with exponential backoff
    - Provider routing via LLMProviderRouter
    - Response validation via LLMResponseValidator
    - Token usage tracking
    - Response saving for debugging
    """

    def __init__(self):
        """Initialize request handler with dependencies"""
        self.provider_router = get_provider_router()
        self.validator = LLMResponseValidator()

    def make_request(
        self,
        stage_name: str,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        token_tracker: Optional[TokenTracker] = None,
        base_path: Optional[str] = None,
        validation_level: str = "minimal",
        custom_validator: Optional[Callable] = None,
        enable_web_search: bool = False,
        post_processor: Optional[Callable[[str, str], Any]] = None,
        **validation_kwargs
    ) -> Tuple[Any, str]:
        """
        Universal LLM request with automatic retry, fallback, validation, and post-processing.

        Args:
            stage_name: Pipeline stage name (e.g., "generate_article")
                        Used for model selection from config if model_name not provided
            messages: Chat messages in OpenAI format [{"role": "user", "content": "..."}]
            model_name: Override model name (default: from LLM_MODELS[stage_name])
            temperature: Model temperature 0.0-1.0 (default: 0.3)
            max_tokens: Maximum tokens to generate (optional)
            response_format: Response format spec, e.g., {"type": "json_object"}
            token_tracker: TokenTracker instance for usage tracking (optional)
            base_path: Base path for saving responses (optional)
            validation_level: "v3", "minimal", "none" (default: "minimal")
            custom_validator: Custom validation function (optional)
            enable_web_search: Enable web search for Google models (default: False)
            post_processor: Optional function(response_text, model_name) -> processed_result
                           If provided, will be called after validation. If it returns None or
                           raises exception, will trigger retry/fallback. Useful for JSON parsing.
            **validation_kwargs: Additional validation parameters
                - target_language: Target language for v3 validation
                - original_length: Original text length for translation validator
                - min_length: Minimum text length override

        Returns:
            Tuple[processed_result|response_object, actual_model_used]
            If post_processor provided: (processed_result, model_name)
            If not: (response_object, model_name)

        Raises:
            Exception: After all retries and fallback models exhausted

        Example without post_processor:
            >>> response, model = make_request(
            ...     stage_name="generate_article",
            ...     messages=[{"role": "user", "content": "Write about AI"}],
            ...     temperature=0.3,
            ...     validation_level="v3"
            ... )
            >>> print(response.choices[0].message.content)

        Example with post_processor (JSON parsing):
            >>> def parse_json(text, model): return json.loads(text)
            >>> parsed_data, model = make_request(
            ...     stage_name="extract_sections",
            ...     messages=messages,
            ...     post_processor=parse_json
            ... )
        """
        # Extract base stage name (handle section-specific stages like "translation_section_1")
        base_stage_name = stage_name.split("_section_")[0] if "_section_" in stage_name else stage_name

        # Determine models to try: primary + fallback
        primary_model = model_name or LLM_MODELS.get(base_stage_name)
        fallback_model = FALLBACK_MODELS.get(base_stage_name)

        if not primary_model:
            raise ValueError(f"No primary model configured for stage '{stage_name}'")

        models_to_try = [primary_model]
        if fallback_model and fallback_model != primary_model:
            models_to_try.append(fallback_model)
            logger.info(f"📌 [{stage_name}] Fallback model available: {fallback_model}")
        else:
            logger.info(f"⚠️ [{stage_name}] No fallback model configured, will only try primary model")

        logger.info(f"🎯 [{stage_name}] Models to try: {models_to_try}")

        # Try each model (primary, then fallback)
        last_exception = None
        for model_index, current_model in enumerate(models_to_try):
            model_label = "primary" if model_index == 0 else "fallback"
            logger.info(f"🤖 [{stage_name}] Trying {model_label} model: {current_model}")

            # Retry loop for current model (3 attempts)
            for attempt in range(1, RETRY_CONFIG["max_attempts"] + 1):
                try:
                    logger.info(f"📝 [{stage_name}] Attempt {attempt}/{RETRY_CONFIG['max_attempts']} with {current_model}")

                    # Make API call via provider router
                    response_obj, provider = self.provider_router.route_request(
                        model_name=current_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                        enable_web_search=enable_web_search
                    )

                    # Save raw response (before validation)
                    if base_path:
                        self._save_raw_response(
                            base_path=base_path,
                            stage_name=stage_name,
                            model_name=current_model,
                            attempt=attempt,
                            response_obj=response_obj
                        )

                    # Extract response text
                    response_text = self._extract_response_text(response_obj)

                    # CRITICAL: Empty response = error (need retry)
                    if not response_text or len(response_text.strip()) == 0:
                        logger.warning(f"⚠️ [{stage_name}] API returned empty content (attempt {attempt})")
                        raise Exception(f"Empty response from model on attempt {attempt}")

                    # Get finish_reason for validation
                    finish_reason = self._extract_finish_reason(response_obj)

                    # Validate response
                    validation_kwargs_copy = validation_kwargs.copy()
                    validation_kwargs_copy["finish_reason"] = finish_reason

                    is_valid = self.validator.validate(
                        response_text=response_text,
                        validation_level=validation_level,
                        custom_validator=custom_validator,
                        **validation_kwargs_copy
                    )

                    if not is_valid:
                        content_preview = response_text[:100] + "..." if len(response_text) > 100 else response_text
                        logger.warning(f"⚠️ [{stage_name}] Validation failed for {current_model} attempt {attempt}")
                        logger.warning(f"   Length: {len(response_text)} chars, Preview: {content_preview}")

                        # Save failed validation response
                        if base_path:
                            self._save_failed_response(
                                base_path=base_path,
                                stage_name=stage_name,
                                model_name=current_model,
                                attempt=attempt,
                                response_text=response_text,
                                error="Validation failed"
                            )

                        raise ValueError("Response validation failed")

                    # Post-processing (if post_processor provided)
                    if post_processor:
                        logger.info(f"🔄 [{stage_name}] Running post-processor...")
                        try:
                            processed_result = post_processor(response_text, current_model)

                            # Check if post-processor returned None
                            if processed_result is None:
                                logger.warning(f"⚠️ [{stage_name}] Post-processor returned None (attempt {attempt})")

                                # Save failed post-processing response
                                if base_path:
                                    self._save_failed_response(
                                        base_path=base_path,
                                        stage_name=stage_name,
                                        model_name=current_model,
                                        attempt=attempt,
                                        response_text=response_text,
                                        error="Post-processor returned None"
                                    )

                                raise ValueError("Post-processor returned None")

                            logger.info(f"✅ [{stage_name}] Post-processing successful")

                            # Track tokens
                            if token_tracker and hasattr(response_obj, 'usage') and response_obj.usage:
                                token_tracker.add_usage(
                                    stage=stage_name,
                                    usage=response_obj.usage,
                                    extra_metadata={
                                        "model": current_model,
                                        "provider": provider,
                                        "attempt": attempt,
                                        "model_label": model_label,
                                        "post_processed": True
                                    }
                                )

                            # Save successful post-processing response
                            if base_path:
                                self._save_successful_response(
                                    base_path=base_path,
                                    stage_name=stage_name,
                                    model_name=current_model,
                                    attempt=attempt,
                                    response_text=response_text,
                                    post_processed=True
                                )

                            # Success with post-processing!
                            logger.info(f"✅ [{stage_name}] Success with {current_model} on attempt {attempt}")
                            return processed_result, current_model

                        except Exception as post_error:
                            logger.warning(f"⚠️ [{stage_name}] Post-processing failed: {post_error}")

                            # Save failed post-processing response
                            if base_path:
                                self._save_failed_response(
                                    base_path=base_path,
                                    stage_name=stage_name,
                                    model_name=current_model,
                                    attempt=attempt,
                                    response_text=response_text,
                                    error=f"Post-processing failed: {post_error}"
                                )

                            raise ValueError(f"Post-processing failed: {post_error}") from post_error
                    else:
                        # No post-processor - return raw response after validation
                        # Track tokens
                        if token_tracker and hasattr(response_obj, 'usage') and response_obj.usage:
                            token_tracker.add_usage(
                                stage=stage_name,
                                usage=response_obj.usage,
                                extra_metadata={
                                    "model": current_model,
                                    "provider": provider,
                                    "attempt": attempt,
                                    "model_label": model_label
                                }
                            )

                        # Save successful response
                        if base_path:
                            self._save_successful_response(
                                base_path=base_path,
                                stage_name=stage_name,
                                model_name=current_model,
                                attempt=attempt,
                                response_text=response_text
                            )

                        # Success!
                        logger.info(f"✅ [{stage_name}] Success with {current_model} on attempt {attempt}")
                        return response_obj, current_model

                except Exception as e:
                    last_exception = e
                    logger.warning(f"❌ [{stage_name}] Attempt {attempt} failed: {str(e)}")

                    # Save error response if we got one
                    if base_path and "response_obj" in locals() and hasattr(response_obj, 'choices'):
                        try:
                            error_response_content = response_obj.choices[0].message.content
                            self._save_failed_response(
                                base_path=base_path,
                                stage_name=stage_name,
                                model_name=current_model,
                                attempt=attempt,
                                response_text=error_response_content,
                                error=str(e)
                            )
                        except Exception as save_error:
                            logger.error(f"❌ Failed to save error response: {save_error}")

                    # Wait before retry (if not last attempt for this model)
                    if attempt < RETRY_CONFIG["max_attempts"]:
                        delay = RETRY_CONFIG["delays"][attempt - 1]
                        logger.info(f"⏳ [{stage_name}] Waiting {delay}s before retry...")
                        time.sleep(delay)

            # All retries exhausted for this model
            logger.error(f"💔 [{stage_name}] All {RETRY_CONFIG['max_attempts']} attempts failed for {current_model}")

        # All models exhausted
        error_msg = (
            f"All models failed for stage '{stage_name}' after {RETRY_CONFIG['max_attempts']} attempts each. "
            f"Tried models: {models_to_try}"
        )
        logger.error(f"🚨 [{stage_name}] {error_msg}")
        raise Exception(error_msg) from last_exception

    def _extract_response_text(self, response_obj: Any) -> str:
        """
        Extract text content from response object.

        Handles different response formats from different providers.

        Args:
            response_obj: API response object

        Returns:
            Extracted text content
        """
        if hasattr(response_obj, 'choices') and response_obj.choices:
            return response_obj.choices[0].message.content
        elif isinstance(response_obj, dict) and "choices" in response_obj:
            return response_obj["choices"][0]["message"]["content"]
        elif isinstance(response_obj, dict) and "text" in response_obj:
            return response_obj["text"]
        else:
            return str(response_obj)

    def _extract_finish_reason(self, response_obj: Any) -> Optional[str]:
        """
        Extract finish_reason from response object.

        Args:
            response_obj: API response object

        Returns:
            Finish reason string or None
        """
        if hasattr(response_obj, 'choices') and response_obj.choices:
            return response_obj.choices[0].finish_reason
        elif isinstance(response_obj, dict) and "choices" in response_obj:
            return response_obj["choices"][0].get("finish_reason")
        else:
            return None

    def _save_raw_response(
        self,
        base_path: str,
        stage_name: str,
        model_name: str,
        attempt: int,
        response_obj: Any
    ):
        """Save raw response object as JSON for debugging"""
        try:
            responses_dir = os.path.join(base_path, "llm_responses_raw")
            os.makedirs(responses_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_obj_file = os.path.join(
                responses_dir,
                f"{stage_name}_raw_obj_attempt{attempt}_{timestamp}.json"
            )

            with open(raw_obj_file, 'w', encoding='utf-8') as f:
                # Try model_dump() first (Pydantic models), then dict(), then str()
                if hasattr(response_obj, 'model_dump'):
                    json.dump(response_obj.model_dump(), f, indent=2, ensure_ascii=False)
                elif hasattr(response_obj, 'dict'):
                    json.dump(response_obj.dict(), f, indent=2, ensure_ascii=False)
                else:
                    f.write(str(response_obj))

            logger.debug(f"💾 RAW RESPONSE saved: {raw_obj_file}")

        except Exception as e:
            logger.error(f"❌ Failed to save raw response: {e}")

    def _save_successful_response(
        self,
        base_path: str,
        stage_name: str,
        model_name: str,
        attempt: int,
        response_text: str,
        post_processed: bool = False
    ):
        """Save successful response with metadata"""
        try:
            responses_dir = os.path.join(base_path, "llm_responses_raw")
            os.makedirs(responses_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            response_file = os.path.join(
                responses_dir,
                f"{stage_name}_response_attempt{attempt}_{timestamp}.txt"
            )

            with open(response_file, 'w', encoding='utf-8') as f:
                f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
                f.write(f"MODEL: {model_name}\n")
                f.write(f"STAGE: {stage_name}\n")
                f.write(f"ATTEMPT: {attempt}\n")
                f.write(f"RESPONSE_LENGTH: {len(response_text)}\n")
                f.write(f"VALIDATION: PASSED\n")
                f.write(f"POST_PROCESSED: {post_processed}\n")
                f.write(f"SUCCESS: True\n")
                f.write("=" * 80 + "\n")
                f.write(response_text)

            logger.debug(f"💾 SUCCESS RESPONSE saved: {response_file}")

        except Exception as e:
            logger.error(f"❌ Failed to save successful response: {e}")

    def _save_failed_response(
        self,
        base_path: str,
        stage_name: str,
        model_name: str,
        attempt: int,
        response_text: str,
        error: str
    ):
        """Save failed response with error info"""
        try:
            responses_dir = os.path.join(base_path, "llm_responses_raw")
            os.makedirs(responses_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            error_file = os.path.join(
                responses_dir,
                f"ERROR_{stage_name}_response_attempt{attempt}_{timestamp}.txt"
            )

            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
                f.write(f"MODEL: {model_name}\n")
                f.write(f"STAGE: {stage_name}\n")
                f.write(f"ATTEMPT: {attempt}\n")
                f.write(f"ERROR: {error}\n")
                f.write(f"RESPONSE_LENGTH: {len(response_text)}\n")
                f.write(f"SUCCESS: False\n")
                f.write("=" * 80 + "\n")
                f.write(response_text)

            logger.debug(f"💾 ERROR RESPONSE saved: {error_file}")

        except Exception as e:
            logger.error(f"❌ Failed to save error response: {e}")


# Global singleton instance
_request_handler = LLMRequestHandler()


def make_llm_request(
    stage_name: str,
    messages: List[Dict[str, str]],
    **kwargs
) -> Tuple[Any, str]:
    """
    Convenience function - wrapper around LLMRequestHandler.

    This is the main entry point for all LLM requests in the pipeline.

    Args:
        stage_name: Pipeline stage name
        messages: Chat messages
        **kwargs: All other parameters (see LLMRequestHandler.make_request)

    Returns:
        Tuple[response_object, actual_model_used]

    Example:
        >>> from src.llm_request import make_llm_request
        >>> response, model = make_llm_request(
        ...     stage_name="generate_article",
        ...     messages=[{"role": "user", "content": "Write about AI"}],
        ...     temperature=0.3,
        ...     validation_level="v3"
        ... )
    """
    return _request_handler.make_request(stage_name, messages, **kwargs)
