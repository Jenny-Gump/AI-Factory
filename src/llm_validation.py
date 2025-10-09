"""
LLM Response Validation System

This module provides a unified validation system for LLM responses with multiple validation levels:
- v3.0: 6-level scientific validation (compression, entropy, bigrams, word density, finish_reason, language)
- minimal: Basic length check (100+ characters)
- none: No validation
- custom: User-provided validation function

Follows SOLID principles:
- Single Responsibility: Each validator checks one aspect
- Open/Closed: Easy to add new validation levels
- Liskov Substitution: All validators return consistent format
- Interface Segregation: Minimal validator interface
- Dependency Inversion: Validation strategy pattern
"""
import gzip
import math
import re
from typing import Tuple, Callable, Optional
from collections import Counter

from src.logger_config import setup_logger

logger = setup_logger(__name__)


class LLMResponseValidator:
    """
    Validates LLM responses with configurable validation levels.

    This class provides multiple validation strategies:
    - v3.0: Scientific multi-level validation
    - minimal: Basic length check
    - none: No validation (always passes)
    - custom: User-provided validation function
    """

    @staticmethod
    def validate(
        response_text: str,
        validation_level: str = "v3",
        custom_validator: Optional[Callable] = None,
        **kwargs
    ) -> bool:
        """
        Validate LLM response with specified validation level.

        Args:
            response_text: Text to validate
            validation_level: "v3", "minimal", or "none"
            custom_validator: Custom validation function (overrides validation_level)
            **kwargs: Additional parameters passed to validator
                - min_length: Minimum text length (default: 300 for v3, 300 for minimal)
                - target_language: Target language for v3 validation
                - finish_reason: API finish reason for v3 validation

        Returns:
            True if valid, False otherwise

        Raises:
            ValueError: If validation_level is unknown
        """
        if validation_level == "none":
            return True

        if custom_validator:
            return custom_validator(response_text, **kwargs)

        if validation_level == "minimal":
            min_length = kwargs.get("min_length", 300)
            return LLMResponseValidator._validate_minimal(response_text, min_length)

        if validation_level == "v3":
            min_length = kwargs.get("min_length", 300)
            target_language = kwargs.get("target_language")
            finish_reason = kwargs.get("finish_reason")
            success, reason = LLMResponseValidator._validate_v3(
                response_text,
                min_length,
                target_language,
                finish_reason
            )
            if not success:
                logger.warning(f"⚠️ v3.0 validation failed: {reason}")
            return success

        raise ValueError(f"Unknown validation level: {validation_level}")

    @staticmethod
    def _validate_minimal(text: str, min_length: int = 300) -> bool:
        """
        Minimal validation: basic length check.

        Args:
            text: Text to validate
            min_length: Minimum required length in characters

        Returns:
            True if text is at least min_length characters, False otherwise
        """
        is_valid = len(text.strip()) >= min_length
        if not is_valid:
            logger.warning(f"⚠️ Minimal validation failed: {len(text)} < {min_length} chars")
        return is_valid

    @staticmethod
    def _validate_v3(
        content: str,
        min_length: int = 300,
        target_language: Optional[str] = None,
        finish_reason: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        v3.0 Multi-level scientific validation.

        Applies 6 research-based methods for spam/garbage detection:
        1. Compression Ratio (gzip) - main defense against any repetitions
        2. Shannon Entropy - information density check
        3. Character Bigrams - protection against short cycles
        4. Word Density - lexical structure validation
        5. Finish Reason - reject MAX_TOKENS/CONTENT_FILTER from API
        6. Language Check - target language verification

        Args:
            content: Text to validate
            min_length: Minimum content length in characters
            target_language: Target language ('ru', 'en', etc.) for language check
            finish_reason: API stop reason (STOP, MAX_TOKENS, etc.)

        Returns:
            Tuple[success: bool, reason: str] - validation result and failure reason

        Examples:
            >>> _validate_v3("Normal text content", 10)
            (True, "ok")
            >>> _validate_v3("о-о-о-о-о..." * 1000, 10)
            (False, "high_compression (8.42)")

        Based on research:
            - Compression ratio for spam detection (Go Fish Digital, 2024)
            - Shannon entropy for text diversity (Stanford NLP, 2024)
            - Kolmogorov complexity approximation (Frontiers Psychology, 2022)
        """
        # 0. BASIC CHECKS
        if not content or not isinstance(content, str):
            logger.warning("Validation failed: empty or invalid content")
            return False, "empty_or_invalid"

        content = content.strip()
        if len(content) < min_length:
            logger.warning(f"Validation failed: too short ({len(content)} < {min_length})")
            return False, f"too_short ({len(content)} < {min_length})"

        # 1. COMPRESSION RATIO (main check - catches ALL types of repetition)
        try:
            original_size = len(content.encode('utf-8'))
            compressed_size = len(gzip.compress(content.encode('utf-8')))
            compression_ratio = original_size / compressed_size

            # Research shows: ratio >4.0 = 50%+ spam probability
            if compression_ratio > 4.0:
                logger.warning(f"Validation failed: high compression ratio {compression_ratio:.2f} (threshold: 4.0)")
                return False, f"high_compression ({compression_ratio:.2f})"
        except Exception as e:
            logger.warning(f"Compression ratio check failed: {e}")

        # 2. SHANNON ENTROPY (information density)
        try:
            counter = Counter(content)
            total = len(content)
            entropy = -sum((count/total) * math.log2(count/total)
                          for count in counter.values())

            # Quality text: entropy 3.5-4.5 bits for English/Russian
            # Repetitive garbage: entropy <2.5
            if entropy < 2.5:
                logger.warning(f"Validation failed: low entropy {entropy:.2f} bits (threshold: 2.5)")
                return False, f"low_entropy ({entropy:.2f})"
        except Exception as e:
            logger.warning(f"Entropy check failed: {e}")

        # 3. CHARACTER BIGRAMS (protection against short cycles like "-о-о-о-")
        try:
            bigrams = [content[i:i+2] for i in range(len(content)-1)]
            if bigrams:
                unique_ratio = len(set(bigrams)) / len(bigrams)

                # If <2% bigrams are unique - strong cycling (spam о-о-о, н-н-н)
                # Threshold lowered from 15% to 2% based on real spam analysis
                # Spam: 0.17-1.06% unique bigrams | Legit: 10%+ unique bigrams
                if unique_ratio < 0.02:
                    logger.warning(f"Validation failed: repetitive bigrams {unique_ratio:.2%} unique (threshold: 2%)")
                    return False, f"repetitive_bigrams ({unique_ratio:.2%})"
        except Exception as e:
            logger.warning(f"Bigram check failed: {e}")

        # 4. WORD DENSITY (lexical structure)
        try:
            words = re.findall(r'\b\w+\b', content)
            if words:
                word_ratio = len(words) / len(content)

                # Quality text: 0.15-0.25 words per character
                # Garbage: <0.05 (few words) or >0.4 (only letters, no spaces)
                if word_ratio < 0.05:
                    logger.warning(f"Validation failed: low word density {word_ratio:.2%} (threshold: 5%)")
                    return False, f"low_word_density ({word_ratio:.2%})"
                if word_ratio > 0.4:
                    logger.warning(f"Validation failed: too high word density {word_ratio:.2%} (threshold: 40%)")
                    return False, f"high_word_density ({word_ratio:.2%})"
            elif len(content) > 100:
                # No words in long text = pure garbage
                logger.warning("Validation failed: no words in long content")
                return False, "no_words"
        except Exception as e:
            logger.warning(f"Word density check failed: {e}")

        # 5. FINISH REASON CHECK (reject API errors)
        if finish_reason:
            valid_reasons = ["STOP", "stop", "END_TURN", "end_turn"]
            if finish_reason not in valid_reasons:
                logger.warning(f"Validation failed: invalid finish_reason='{finish_reason}' (expected: {valid_reasons})")
                return False, f"bad_finish_reason ({finish_reason})"

        # 6. LANGUAGE CHECK (target language verification)
        if target_language:
            try:
                # Russian: check Cyrillic
                if target_language.lower() in ['ru', 'russian', 'русский']:
                    cyrillic_chars = sum(1 for c in content if '\u0400' <= c <= '\u04FF')
                    cyrillic_ratio = cyrillic_chars / len(content)
                    if cyrillic_ratio < 0.3:
                        logger.warning(f"Validation failed: not Russian text ({cyrillic_ratio:.1%} cyrillic, threshold: 30%)")
                        return False, f"not_russian ({cyrillic_ratio:.1%})"

                # English: check Latin
                elif target_language.lower() in ['en', 'english', 'английский']:
                    latin_chars = sum(1 for c in content if 'a' <= c.lower() <= 'z')
                    latin_ratio = latin_chars / len(content)
                    if latin_ratio < 0.5:
                        logger.warning(f"Validation failed: not English text ({latin_ratio:.1%} latin, threshold: 50%)")
                        return False, f"not_english ({latin_ratio:.1%})"

                # Spanish: check Latin
                elif target_language.lower() in ['es', 'spanish', 'español', 'испанский']:
                    latin_chars = sum(1 for c in content if 'a' <= c.lower() <= 'z')
                    latin_ratio = latin_chars / len(content)
                    if latin_ratio < 0.5:
                        logger.warning(f"Validation failed: not Spanish text ({latin_ratio:.1%} latin, threshold: 50%)")
                        return False, f"not_spanish ({latin_ratio:.1%})"

                # German: check Latin
                elif target_language.lower() in ['de', 'german', 'deutsch', 'немецкий']:
                    latin_chars = sum(1 for c in content if 'a' <= c.lower() <= 'z')
                    latin_ratio = latin_chars / len(content)
                    if latin_ratio < 0.5:
                        logger.warning(f"Validation failed: not German text ({latin_ratio:.1%} latin, threshold: 50%)")
                        return False, f"not_german ({latin_ratio:.1%})"

                # French: check Latin
                elif target_language.lower() in ['fr', 'french', 'français', 'французский']:
                    latin_chars = sum(1 for c in content if 'a' <= c.lower() <= 'z')
                    latin_ratio = latin_chars / len(content)
                    if latin_ratio < 0.5:
                        logger.warning(f"Validation failed: not French text ({latin_ratio:.1%} latin, threshold: 50%)")
                        return False, f"not_french ({latin_ratio:.1%})"

                else:
                    # For unknown languages - skip language check
                    logger.debug(f"Language check skipped for '{target_language}' (not in supported list)")

            except Exception as e:
                logger.warning(f"Language check failed: {e}")

        # All checks passed
        logger.debug(f"Content validation passed: {len(content)} chars, compression={compression_ratio:.2f}, entropy={entropy:.2f}")
        return True, "ok"


# Custom validators for specific stages

def translation_validator(text: str, original_length: int, **kwargs) -> bool:
    """
    Custom validator for translation stage.

    Checks:
    1. v3.0 validation (all 6 levels)
    2. Length ratio check (80-125% of original)

    Args:
        text: Translated text
        original_length: Length of original text before translation
        **kwargs: Additional parameters (target_language, finish_reason, etc.)

    Returns:
        True if valid, False otherwise
    """
    # First run v3.0 validation
    min_length = kwargs.get("min_length", 300)
    target_language = kwargs.get("target_language")
    finish_reason = kwargs.get("finish_reason")

    success, reason = LLMResponseValidator._validate_v3(
        text,
        min_length,
        target_language,
        finish_reason
    )

    if not success:
        logger.warning(f"⚠️ Translation v3.0 validation failed: {reason}")
        return False

    # Then check length ratio (80-125% of original)
    current_length = len(text)
    ratio = current_length / original_length if original_length > 0 else 0

    if ratio < 0.8:
        logger.warning(f"⚠️ Translation too short: {ratio:.1%} of original (min: 80%)")
        return False

    if ratio > 1.25:
        logger.warning(f"⚠️ Translation too long: {ratio:.1%} of original (max: 125%)")
        return False

    logger.info(f"✅ Translation validation passed: {ratio:.1%} of original length")
    return True
