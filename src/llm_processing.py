import os
import json
import re
import time
import asyncio
import requests
from datetime import datetime
from typing import List, Dict, Any, Union
from dotenv import load_dotenv
import openai

from src.logger_config import logger
from src.token_tracker import TokenTracker
from src.config import LLM_MODELS, DEFAULT_MODEL, LLM_PROVIDERS, get_provider_for_model, FALLBACK_MODELS, RETRY_CONFIG, SECTION_TIMEOUT, MODEL_TIMEOUT, SECTION_MAX_RETRIES
from src.llm_request import make_llm_request

# Загружаем переменные среды
load_dotenv()

# Словарь для кэширования клиентов
_clients_cache = {}

def clean_llm_tokens(text: str) -> str:
    """Remove LLM-specific tokens from generated content."""
    if not text:
        return text

    # Токены для удаления (специфичные для разных LLM)
    tokens_to_remove = [
        '<｜begin▁of▁sentence｜>',
        '<|begin_of_sentence|>',
        '<｜end▁of▁sentence｜>',
        '<|end_of_sentence|>',
        '<|im_start|>',
        '<|im_end|>',
        '<|end|>',
        '<<SYS>>',
        '<</SYS>>',
        '[INST]',
        '[/INST]'
    ]

    cleaned = text
    for token in tokens_to_remove:
        cleaned = cleaned.replace(token, '')

    # Убираем лишние пробелы и переводы строк
    return cleaned.strip()


# ============================================================================
# POST-PROCESSORS for unified retry/fallback system
# ============================================================================

def _editorial_post_processor(response_text: str, model_name: str):
    """
    Post-processor for editorial_review stage.

    Cleans LLM tokens and parses JSON response with normalization.

    Args:
        response_text: Raw LLM response text
        model_name: Name of model that generated the response

    Returns:
        Parsed Dict with article data, or None if parsing failed
    """
    # Clean LLM tokens first
    cleaned_text = clean_llm_tokens(response_text)

    # Parse JSON with normalization (5 attempts inside _try_parse_editorial_json)
    parsed = _try_parse_editorial_json(cleaned_text, model_name, 1, "final")

    return parsed  # None if all parsing attempts failed


def _extract_post_processor(response_text: str, model_name: str):
    """
    Post-processor for extract_sections stage.

    Cleans LLM tokens and parses JSON response to list of structures.

    Args:
        response_text: Raw LLM response text
        model_name: Name of model that generated the response

    Returns:
        List[Dict] of extracted structures, or None if parsing failed
    """
    # Clean LLM tokens first
    cleaned_text = clean_llm_tokens(response_text)

    # Parse JSON (handles arrays, objects, and wrapped formats)
    parsed = _parse_json_from_response(cleaned_text)

    # Validate result is a list
    if not isinstance(parsed, list):
        logger.warning(f"_extract_post_processor: Expected list, got {type(parsed)}")
        return None

    return parsed


def _create_structure_post_processor(response_text: str, model_name: str):
    """
    Post-processor for create_structure stage.

    Parses JSON response and validates structure format.
    Returns None on failure to trigger automatic retry/fallback.

    Args:
        response_text: Raw LLM response text
        model_name: Name of model that generated response

    Returns:
        Normalized ultimate_structure dict or None to trigger retry
    """
    try:
        # Use existing JSON parsing function
        parsed = _parse_json_from_response(response_text)

        # Validate: should be dict or list
        if not parsed or parsed == []:
            logger.warning(f"_create_structure_post_processor: Empty result from {model_name}")
            return None

        # Normalize structure format
        if isinstance(parsed, list):
            logger.warning("⚠️ LLM returned array instead of object - normalizing")
            parsed = {
                "article_structure": parsed,
                "writing_guidelines": {}
            }
        elif isinstance(parsed, dict):
            if "article_structure" not in parsed:
                logger.warning("⚠️ Missing 'article_structure' key - normalizing")
                parsed = {
                    "article_structure": parsed.get("sections", [parsed]),
                    "writing_guidelines": parsed.get("writing_guidelines", {})
                }

        return parsed

    except Exception as e:
        logger.warning(f"_create_structure_post_processor: Failed to parse JSON from {model_name}: {e}")
        return None  # Trigger retry/fallback


def validate_content_quality_v3(content: str, min_length: int = 300,
                                target_language: str = None,
                                finish_reason: str = None) -> tuple:
    """
    Многоуровневая валидация качества LLM контента (v3.0).

    Применяет 6 научно-обоснованных методов детекции спама/мусора:
    1. Compression Ratio (gzip) - основная защита от повторений любой длины
    2. Shannon Entropy - проверка информационной плотности контента
    3. Character N-grams - защита от коротких циклов (1-2 символа)
    4. Word Density - проверка лексической структуры текста
    5. Finish Reason - отклонение MAX_TOKENS/CONTENT_FILTER от API
    6. Language Check - проверка соответствия целевому языку

    Args:
        content: Текст для проверки
        min_length: Минимальная длина полезного контента в символах
        target_language: Целевой язык ('ru', 'en', etc.) - для проверки соответствия
        finish_reason: Причина остановки генерации от API (STOP, MAX_TOKENS, etc.)

    Returns:
        tuple: (success: bool, reason: str) - результат проверки и причина отклонения

    Examples:
        >>> validate_content_quality_v3("Normal text content", 10)
        (True, "ok")
        >>> validate_content_quality_v3("о-о-о-о-о..." * 1000, 10)
        (False, "high_compression (8.42)")

    Based on research:
        - Compression ratio for spam detection (Go Fish Digital, 2024)
        - Shannon entropy for text diversity (Stanford NLP, 2024)
        - Kolmogorov complexity approximation (Frontiers Psychology, 2022)
    """
    import gzip
    import math
    import re
    from collections import Counter

    # 0. БАЗОВЫЕ ПРОВЕРКИ
    if not content or not isinstance(content, str):
        logger.warning("Validation failed: empty or invalid content")
        return False, "empty_or_invalid"

    content = content.strip()
    if len(content) < min_length:
        logger.warning(f"Validation failed: too short ({len(content)} < {min_length})")
        return False, f"too_short ({len(content)} < {min_length})"

    # 1. COMPRESSION RATIO (главная проверка - ловит ВСЕ типы повторений)
    try:
        original_size = len(content.encode('utf-8'))
        compressed_size = len(gzip.compress(content.encode('utf-8')))
        compression_ratio = original_size / compressed_size

        # Исследования показывают: ratio >4.0 = 50%+ вероятность спама
        if compression_ratio > 4.0:
            logger.warning(f"Validation failed: high compression ratio {compression_ratio:.2f} (threshold: 4.0)")
            return False, f"high_compression ({compression_ratio:.2f})"
    except Exception as e:
        logger.warning(f"Compression ratio check failed: {e}")

    # 2. SHANNON ENTROPY (информационная плотность)
    try:
        counter = Counter(content)
        total = len(content)
        entropy = -sum((count/total) * math.log2(count/total)
                      for count in counter.values())

        # Качественный текст: entropy 3.5-4.5 bits для английского/русского
        # Повторяющийся мусор: entropy <2.5
        if entropy < 2.5:
            logger.warning(f"Validation failed: low entropy {entropy:.2f} bits (threshold: 2.5)")
            return False, f"low_entropy ({entropy:.2f})"
    except Exception as e:
        logger.warning(f"Entropy check failed: {e}")

    # 3. CHARACTER BIGRAMS (защита от коротких циклов как "-о-о-о-")
    try:
        bigrams = [content[i:i+2] for i in range(len(content)-1)]
        if bigrams:
            unique_ratio = len(set(bigrams)) / len(bigrams)

            # Если <2% биграмм уникальны - сильное зацикливание (спам о-о-о, н-н-н)
            # Порог снижен с 15% до 2% на основе анализа реального спама и легитимного контента
            # Спам: 0.17-1.06% unique bigrams | Легитим: 10%+ unique bigrams
            if unique_ratio < 0.02:
                logger.warning(f"Validation failed: repetitive bigrams {unique_ratio:.2%} unique (threshold: 2%)")
                return False, f"repetitive_bigrams ({unique_ratio:.2%})"
    except Exception as e:
        logger.warning(f"Bigram check failed: {e}")

    # 4. WORD DENSITY (лексическая структура)
    try:
        words = re.findall(r'\b\w+\b', content)
        if words:
            word_ratio = len(words) / len(content)

            # Качественный текст: 0.15-0.25 слов на символ
            # Мусор: <0.05 (мало слов) или >0.4 (одни буквы без пробелов)
            if word_ratio < 0.05:
                logger.warning(f"Validation failed: low word density {word_ratio:.2%} (threshold: 5%)")
                return False, f"low_word_density ({word_ratio:.2%})"
            if word_ratio > 0.4:
                logger.warning(f"Validation failed: too high word density {word_ratio:.2%} (threshold: 40%)")
                return False, f"high_word_density ({word_ratio:.2%})"
        elif len(content) > 100:
            # Нет слов в длинном тексте = чистый мусор
            logger.warning("Validation failed: no words in long content")
            return False, "no_words"
    except Exception as e:
        logger.warning(f"Word density check failed: {e}")

    # 5. FINISH REASON CHECK (отклонение API ошибок)
    if finish_reason:
        valid_reasons = ["STOP", "stop", "END_TURN", "end_turn"]
        if finish_reason not in valid_reasons:
            logger.warning(f"Validation failed: invalid finish_reason='{finish_reason}' (expected: {valid_reasons})")
            return False, f"bad_finish_reason ({finish_reason})"

    # 6. LANGUAGE CHECK (проверка целевого языка)
    if target_language:
        try:
            # Русский: проверка кириллицы
            if target_language.lower() in ['ru', 'russian', 'русский']:
                cyrillic_chars = sum(1 for c in content if '\u0400' <= c <= '\u04FF')
                cyrillic_ratio = cyrillic_chars / len(content)
                if cyrillic_ratio < 0.3:
                    logger.warning(f"Validation failed: not Russian text ({cyrillic_ratio:.1%} cyrillic, threshold: 30%)")
                    return False, f"not_russian ({cyrillic_ratio:.1%})"

            # Английский: проверка латиницы
            elif target_language.lower() in ['en', 'english', 'английский']:
                latin_chars = sum(1 for c in content if 'a' <= c.lower() <= 'z')
                latin_ratio = latin_chars / len(content)
                if latin_ratio < 0.5:
                    logger.warning(f"Validation failed: not English text ({latin_ratio:.1%} latin, threshold: 50%)")
                    return False, f"not_english ({latin_ratio:.1%})"

            # Испанский: проверка латиницы
            elif target_language.lower() in ['es', 'spanish', 'español', 'испанский']:
                latin_chars = sum(1 for c in content if 'a' <= c.lower() <= 'z')
                latin_ratio = latin_chars / len(content)
                if latin_ratio < 0.5:
                    logger.warning(f"Validation failed: not Spanish text ({latin_ratio:.1%} latin, threshold: 50%)")
                    return False, f"not_spanish ({latin_ratio:.1%})"

            # Немецкий: проверка латиницы
            elif target_language.lower() in ['de', 'german', 'deutsch', 'немецкий']:
                latin_chars = sum(1 for c in content if 'a' <= c.lower() <= 'z')
                latin_ratio = latin_chars / len(content)
                if latin_ratio < 0.5:
                    logger.warning(f"Validation failed: not German text ({latin_ratio:.1%} latin, threshold: 50%)")
                    return False, f"not_german ({latin_ratio:.1%})"

            # Французский: проверка латиницы
            elif target_language.lower() in ['fr', 'french', 'français', 'французский']:
                latin_chars = sum(1 for c in content if 'a' <= c.lower() <= 'z')
                latin_ratio = latin_chars / len(content)
                if latin_ratio < 0.5:
                    logger.warning(f"Validation failed: not French text ({latin_ratio:.1%} latin, threshold: 50%)")
                    return False, f"not_french ({latin_ratio:.1%})"

            else:
                # Для неизвестных языков - skip language check
                logger.debug(f"Language check skipped for '{target_language}' (not in supported list)")

        except Exception as e:
            logger.warning(f"Language check failed: {e}")

    # Все проверки пройдены
    logger.debug(f"Content validation passed: {len(content)} chars, compression={compression_ratio:.2f}, entropy={entropy:.2f}")
    return True, "ok"


# Legacy function for backward compatibility - redirects to v3
def validate_content_quality(content: str, min_length: int = 50) -> bool:
    """
    DEPRECATED: Use validate_content_quality_v3() instead.

    Legacy wrapper for backward compatibility with old code.
    Returns only boolean (True/False) without reason string.
    """
    success, _ = validate_content_quality_v3(content, min_length)
    return success


# validate_content_with_dictionary removed - regex validation is sufficient


def clear_llm_clients_cache():
    """Очищает кэш LLM клиентов для освобождения памяти."""
    global _clients_cache
    _clients_cache.clear()
    logger.info("LLM clients cache cleared")

def get_llm_client(model_name: str) -> Union[openai.OpenAI, str]:
    """Get appropriate LLM client for the given model. Returns 'google_direct' for Google's native API."""
    provider = get_provider_for_model(model_name)

    # Special handling for Google's direct API
    if provider == "google_direct":
        return "google_direct"  # Signal to use direct HTTP requests

    # Return cached client if available
    if provider in _clients_cache:
        return _clients_cache[provider]

    provider_config = LLM_PROVIDERS[provider]
    api_key = os.getenv(provider_config["api_key_env"])

    if not api_key:
        raise ValueError(f"API key not found for provider {provider}. Check {provider_config['api_key_env']} in .env")

    # Create client with provider-specific configuration
    client_kwargs = {
        "api_key": api_key,
        "base_url": provider_config["base_url"]
    }

    # Add extra headers for OpenRouter
    if "extra_headers" in provider_config:
        client_kwargs["default_headers"] = provider_config["extra_headers"]

    client = openai.OpenAI(**client_kwargs)

    # Cache the client
    _clients_cache[provider] = client

    return client

def save_llm_interaction(base_path: str, stage_name: str, messages: List[Dict], 
                         response: str, request_id: str = None, extra_params: Dict = None):
    """
    Сохраняет запрос и ответ LLM для отладки и анализа.
    
    Args:
        base_path: Базовый путь для сохранения (например, paths["extraction"])
        stage_name: Название этапа (например, "extract_sections")
        messages: Сообщения, отправленные в LLM
        response: Сырой ответ от LLM
        request_id: ID запроса для множественных запросов (например, source_1)
        extra_params: Дополнительные параметры запроса
    """
    try:
        # Создаём подпапки для запросов и ответов
        requests_dir = os.path.join(base_path, "llm_requests")
        responses_dir = os.path.join(base_path, "llm_responses_raw")
        os.makedirs(requests_dir, exist_ok=True)
        os.makedirs(responses_dir, exist_ok=True)
        
        # Формируем имена файлов
        if request_id:
            request_filename = f"{request_id}_request.json"
            response_filename = f"{request_id}_response.txt"
        else:
            request_filename = f"{stage_name}_request.json"
            response_filename = f"{stage_name}_response.txt"
        
        # Подготавливаем данные запроса
        request_data = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage_name,
            "model": extra_params.get("model", DEFAULT_MODEL) if extra_params else DEFAULT_MODEL,
            "messages": messages,
            "extra_params": extra_params or {}
        }
        
        # Сохраняем запрос
        request_path = os.path.join(requests_dir, request_filename)
        with open(request_path, 'w', encoding='utf-8') as f:
            json.dump(request_data, f, indent=2, ensure_ascii=False)
        
        # DEBUG: Log response size before saving
        logger.info(f"🔍 SAVE_LLM_INTERACTION RESPONSE: {len(response)} chars")

        # Сохраняем ответ
        response_path = os.path.join(responses_dir, response_filename)
        with open(response_path, 'w', encoding='utf-8') as f:
            f.write(response)

        # DEBUG: Verify file size after writing
        written_size = os.path.getsize(response_path)
        logger.info(f"🔍 WRITTEN FILE SIZE: {written_size} bytes")

        logger.info(f"Saved LLM interaction: {request_path} + {response_path}")
        
    except Exception as e:
        logger.error(f"Failed to save LLM interaction: {e}")

def _parse_json_from_response(response_content: str, stage_context: str = "unknown") -> Any:
    """
    УМНАЯ ПАРСИНГ ФУНКЦИЯ с логикой определения нужного формата.

    ДЕФОЛТНЫЕ ФОРМАТЫ ПО ЭТАПАМ:
    - ultimate_structure: объект {"article_structure": [...], "writing_guidelines": {...}}
    - extract_sections: массив структур [{"section_title": ..., ...}, ...]
    - other stages: чаще массив, иногда объект

    Args:
        response_content: Сырой ответ от LLM
        stage_context: Контекст этапа для определения ожидаемого формата
    """
    response_content = response_content.strip()

    if not response_content:
        logger.error("Empty response content")
        return []

    # FIRST: Remove markdown code blocks if present (before any parsing attempts)
    if response_content.startswith('```json\n') and response_content.endswith('\n```'):
        response_content = response_content[8:-4].strip()
        logger.info("Removed ```json markdown wrapper")
    elif response_content.startswith('```\n') and response_content.endswith('\n```'):
        response_content = response_content[4:-4].strip()
        logger.info("Removed ``` markdown wrapper")

    # Fix common JSON errors from DeepSeek
    if ',"{"' in response_content or '},"' in response_content:
        # Pattern 1: },"{"section_title" -> },{"section_title"
        response_content = response_content.replace('},"{"', '},{')
        # Pattern 2: }," "writing_guidelines" -> },"writing_guidelines"
        response_content = response_content.replace('}," "', '},"')
        logger.info("Fixed DeepSeek JSON delimiter issues")

    # Remove any standalone quotes between array elements using regex
    import re
    response_content = re.sub(r'\},\s*"\s*\{', '},{', response_content)

    # Attempt 1: Parse as-is and apply SMART FORMATTING
    try:
        parsed = json.loads(response_content)

        if isinstance(parsed, list):
            logger.info("Parsed valid array - returning as-is")
            return parsed
        elif isinstance(parsed, dict):
            # SMART LOGIC: Определяем нужен ли фоллбек по содержимому

            # Для ultimate_structure - ожидаем объект с article_structure + writing_guidelines
            if "article_structure" in parsed and "writing_guidelines" in parsed:
                logger.info("Detected ultimate_structure format - returning object as-is")
                return parsed  # НЕ ОБОРАЧИВАЕМ! Возвращаем как есть

            # Если есть ключ data - используем его содержимое
            elif "data" in parsed:
                logger.info("Found 'data' key - extracting content")
                return parsed["data"]

            # Иначе это одиночный объект структуры - оборачиваем в массив для обратной совместимости
            else:
                logger.info("Single structure object - wrapping in array")
                return [parsed]
        else:
            logger.warning(f"Unexpected parsed type: {type(parsed)}")
            return []

    except json.JSONDecodeError as e:
        logger.warning(f"Standard JSON parsing failed: {e}")
        # Продолжаем к фоллбекам
        pass
    
    # Attempt 1.5: Enhanced JSON preprocessing (for editorial review control characters)
    try:
        logger.info("Attempting enhanced JSON parsing...")
        fixed_content = response_content

        # Fix DeepSeek model specific JSON bugs
        fixed_content = re.sub(r'"context_after: "', r'"context_after": "', fixed_content)
        fixed_content = re.sub(r'"context_before: "', r'"context_before": "', fixed_content)
        fixed_content = re.sub(r'"anchor_text: "', r'"anchor_text": "', fixed_content)
        fixed_content = re.sub(r'"query: "', r'"query": "', fixed_content)
        fixed_content = re.sub(r'"hint: "', r'"hint": "', fixed_content)
        fixed_content = re.sub(r'"section: "', r'"section": "', fixed_content)
        fixed_content = re.sub(r'"ref_id: "', r'"ref_id": "', fixed_content)

        # Generic fix for missing colons in JSON keys
        fixed_content = re.sub(r'"([^"]+): (["\[\{])', r'"\1": \2', fixed_content)

        # Fix control characters that cause "Invalid control character" errors
        # Replace unescaped control characters within JSON string values
        fixed_content = re.sub(r'(:\s*")([^"]*?)(")', lambda m: m.group(1) + m.group(2).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + m.group(3), fixed_content)

        # Additional fix for code blocks with unescaped newlines (common in editorial review responses)
        fixed_content = re.sub(r'(<(?:pre><)?code[^>]*>)(.*?)(</code>(?:</pre>)?)',
                              lambda m: m.group(1) + m.group(2).replace('\n', '\\n') + m.group(3),
                              fixed_content, flags=re.DOTALL)
        
        # Fix escaped underscores in JSON keys (aggressive approach)
        fixed_content = fixed_content.replace('prompt\\_text', 'prompt_text')
        fixed_content = fixed_content.replace('expert\\_description', 'expert_description')
        fixed_content = fixed_content.replace('why\\_good', 'why_good')
        fixed_content = fixed_content.replace('how\\_to\\_improve', 'how_to_improve')
        
        # Fix any remaining backslash-underscore patterns
        fixed_content = re.sub(r'\\\\_', '_', fixed_content)

        # Fix DeepSeek JSON array separator bug: }], { → }, {
        fixed_content = re.sub(r'\}],\s*\{', '}, {', fixed_content)

        # Fix unescaped quotes within JSON string values (common in HTML content)
        # More aggressive approach for long strings with multiple quotes
        def fix_quotes_in_json_string(match):
            key_part = match.group(1)  # "key": "
            content = match.group(2)   # string content
            end_quote = match.group(3) # closing "

            # Handle already escaped quotes
            content = content.replace('\\"', 'TEMP_ESCAPED_QUOTE')
            # Escape unescaped quotes
            content = content.replace('"', '\\"')
            # Restore previously escaped quotes
            content = content.replace('TEMP_ESCAPED_QUOTE', '\\"')

            return key_part + content + end_quote

        # Pattern for JSON string values - more comprehensive
        fixed_content = re.sub(r'(:\s*")([^"]*(?:\\"[^"]*)*)(")(?=\s*[,}])',
                              fix_quotes_in_json_string, fixed_content, flags=re.DOTALL)
        
        parsed = json.loads(fixed_content)
        if isinstance(parsed, list):
            logger.info("Successfully parsed JSON after enhanced preprocessing")
            return parsed
        elif isinstance(parsed, dict):
            logger.info("Successfully parsed JSON after enhanced preprocessing")

            # APPLY SAME SMART LOGIC as in Attempt 1
            # Для ultimate_structure - ожидаем объект с article_structure + writing_guidelines
            if "article_structure" in parsed and "writing_guidelines" in parsed:
                logger.info("Detected ultimate_structure format after preprocessing - returning object as-is")
                return parsed  # НЕ ОБОРАЧИВАЕМ!
            elif "data" in parsed:
                return parsed["data"]
            else:
                return [parsed]  # Оборачиваем одиночные структуры
        else:
            return []
    except json.JSONDecodeError as e:
        logger.warning(f"Enhanced JSON parsing failed: {e}")

        # СОХРАНЕНИЕ ПОВРЕЖДЕННОГО JSON будет в папке этапа при вызове из функций с base_path
        logger.error(f"Enhanced JSON parsing failed: {e} - Response length: {len(response_content)}")

        pass
    
    # Attempt 2: If it looks like a single object, wrap it in an array
    if response_content.startswith('{') and response_content.endswith('}'):
        try:
            obj = json.loads(response_content)
            return [obj]
        except json.JSONDecodeError:
            pass
    
    # Attempt 3: Find JSON blocks in text using regex
    json_pattern = r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
    matches = re.findall(json_pattern, response_content)
    if matches:
        parsed_objects = []
        for match in matches:
            try:
                obj = json.loads(match)
                parsed_objects.append(obj)
            except json.JSONDecodeError:
                continue
        if parsed_objects:
            return parsed_objects
    
    # Attempt 4: Try to fix common JSON errors
    fixed_content = response_content
    # Fix unescaped quotes in values
    fixed_content = re.sub(r'(?<=: ")(.*?)(?="[,}\]])', lambda m: m.group(1).replace('"', '\\"'), fixed_content)
    # Fix trailing commas
    fixed_content = re.sub(r',\s*([}\]])', r'\1', fixed_content)
    
    try:
        parsed = json.loads(fixed_content)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            # APPLY SAME SMART LOGIC as in other attempts
            if "article_structure" in parsed and "writing_guidelines" in parsed:
                logger.info("Detected ultimate_structure format in error recovery - returning object as-is")
                return parsed
            elif "data" in parsed:
                return parsed["data"]
            else:
                return [parsed]
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse extracted JSON string: {e}")
        logger.error(f"String: {response_content[:1000]}")
        return []


def _load_and_prepare_messages(content_type: str, prompt_name: str, replacements: Dict[str, str],
                               variables_manager=None, stage_name: str = None) -> List[Dict]:
    """
    Loads a prompt template, performs replacements, adds variable addons, and splits into messages.

    Args:
        content_type: Type of content (basic_articles, guides, etc.)
        prompt_name: Name of the prompt file (without .txt)
        replacements: Dictionary of placeholder replacements
        variables_manager: Optional VariablesManager instance for injecting variables
        stage_name: Name of the current pipeline stage for variable lookup

    Returns:
        List of message dictionaries for LLM
    """
    path = os.path.join("prompts", content_type, f"{prompt_name}.txt")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            template = f.read()

        # ADD VARIABLES TO REPLACEMENTS
        if variables_manager:
            variables = variables_manager.get_variables_for_replacement()
            # Merge with existing replacements, existing take priority
            replacements = {**variables, **replacements}
            logger.debug(f"Added {len(variables)} variable(s) to replacements")

        for key, value in replacements.items():
            template = template.replace(f"{{{key}}}", str(value))

        lines = template.splitlines()
        system_content = ""
        user_content_lines = []

        if lines and lines[0].startswith("System:"):
            system_content = lines[0].replace("System:", "").strip()
            user_content_lines = lines[1:]
        else:
            user_content_lines = lines

        # Объединяем все строки кроме системной
        full_user_content = "\n".join(user_content_lines)

        # Заменяем маркер "User:" на пустоту, но сохраняем весь контент
        if "User:" in full_user_content:
            # Разделяем по "User:" и объединяем все части
            parts = full_user_content.split("User:")
            user_content = parts[0] + parts[1] if len(parts) == 2 else full_user_content
            user_content = user_content.strip()
        else:
            user_content = full_user_content

        messages = []
        if system_content:
            messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": user_content})

        return messages

    except FileNotFoundError:
        logger.error(f"Prompt file not found: {path}")
        raise


async def _make_llm_request_with_timeout(stage_name: str, model_name: str, messages: list,
                                        token_tracker: TokenTracker = None, timeout: int = MODEL_TIMEOUT,
                                        base_path: str = None, **kwargs) -> tuple:
    """
    Makes LLM request with timeout protection only.

    Retry/fallback logic is fully handled by the unified LLM request system (make_llm_request).
    This function only adds asyncio timeout protection for long-running requests.

    Returns:
        tuple: (response_obj, actual_model_used)

    Raises:
        asyncio.TimeoutError: If request exceeds timeout
        Exception: If request fails after all retry/fallback attempts
    """
    try:
        # Make request with timeout wrapper
        def make_request():
            return make_llm_request(
                stage_name=stage_name,
                model_name=model_name,
                messages=messages,
                token_tracker=token_tracker,
                base_path=base_path,
                validation_level="v3",
                **kwargs
            )

        loop = asyncio.get_event_loop()
        response_obj, actual_model = await asyncio.wait_for(
            loop.run_in_executor(None, make_request),
            timeout=timeout
        )

        logger.info(f"✅ Request completed successfully within {timeout}s timeout")
        return response_obj, actual_model

    except asyncio.TimeoutError:
        logger.error(f"⏰ TIMEOUT: Request exceeded {timeout}s timeout for {stage_name}", exc_info=True)
        raise Exception(f"Request timed out after {timeout}s for {stage_name}")

    except Exception as e:
        logger.error(f"❌ Request failed for {stage_name}: {e}", exc_info=True)
        raise


def _make_google_direct_request(model_name: str, messages: list, **kwargs):
    """
    Makes direct HTTP request to Google Gemini API with proper format conversion.
    Converts OpenAI messages format to Google's contents format.
    """
    from types import SimpleNamespace

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    headers = {
        "Content-Type": "application/json"
    }

    # Convert OpenAI messages format to Google contents format
    system_content = ""
    user_content = ""

    for message in messages:
        if message["role"] == "system":
            system_content = message["content"]
        elif message["role"] == "user":
            user_content = message["content"]

    # Combine system and user content for Google format
    combined_content = f"{system_content}\n\n{user_content}" if system_content else user_content

    # Build Google API request
    request_data = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": combined_content
                    }
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 65536,  # Maximum for Gemini 2.5 Flash (was 30000)
            "temperature": kwargs.get("temperature", 0.3),
            "topP": 0.8,
            "topK": 40
        }
    }

    # Add web search tools for fact-checking
    if model_name == "gemini-2.5-flash":
        request_data["tools"] = [
            {
                "google_search": {}
            }
        ]

    response = requests.post(url, headers=headers, json=request_data)

    if response.status_code != 200:
        raise Exception(f"Google API error: HTTP {response.status_code} - {response.text}")

    result = response.json()

    # DEBUG: Log raw API response size
    logger.info(f"🔍 RAW API RESPONSE: {len(response.text)} chars")

    # DEBUG: Log JSON structure (minimal)
    import json
    json_str = json.dumps(result, indent=2, ensure_ascii=False)
    logger.info(f"🔍 FULL JSON SIZE: {len(json_str)} chars")

    if "candidates" not in result or not result["candidates"]:
        raise Exception("No candidates in Google API response")

    candidate = result["candidates"][0]

    if "content" not in candidate:
        raise Exception("No content in Google API response")

    # CRITICAL FIX: Gemini can return multiple parts, we need to combine them!
    parts = candidate["content"]["parts"]
    logger.info(f"🔍 Gemini returned {len(parts)} part(s) in response")

    # DEBUG: Log full candidate structure to understand what we're getting
    logger.info(f"🔍 CANDIDATE KEYS: {list(candidate.keys())}")
    logger.info(f"🔍 CONTENT KEYS: {list(candidate['content'].keys())}")

    # Combine all text parts
    content_parts = []
    for idx, part in enumerate(parts):
        logger.info(f"🔍 Part {idx+1} keys: {list(part.keys())}")
        if "text" in part:
            part_text = part["text"]
            content_parts.append(part_text)
            logger.info(f"   Part {idx+1}: {len(part_text)} chars")
            logger.info(f"   Part {idx+1} preview: {part_text[:100]}...")
        else:
            logger.warning(f"⚠️ Part {idx+1} has no 'text' field: {part}")

    content = "".join(content_parts)
    logger.info(f"📏 Total combined content: {len(content)} chars")

    # DEBUG: Check if there's content in other places
    if len(content) < 1000:  # If content is suspiciously small
        logger.warning(f"⚠️ SUSPICIOUSLY SMALL CONTENT! Dumping full candidate structure:")
        import json
        logger.warning(f"🔍 FULL CANDIDATE: {json.dumps(candidate, indent=2, ensure_ascii=False)[:2000]}...")

    # Create OpenAI-compatible response object
    response_obj = SimpleNamespace()
    response_obj.choices = [SimpleNamespace()]
    response_obj.choices[0].message = SimpleNamespace()
    response_obj.choices[0].message.content = content
    response_obj.choices[0].finish_reason = candidate.get("finishReason", "stop")

    # DEBUG: Log final response object content size
    logger.info(f"🔍 FINAL RESPONSE_OBJ CONTENT: {len(response_obj.choices[0].message.content)} chars")

    # Create usage info (estimated from content length)
    response_obj.usage = SimpleNamespace()
    response_obj.usage.prompt_tokens = len(combined_content) // 4  # Rough estimate
    response_obj.usage.completion_tokens = len(content) // 4
    response_obj.usage.total_tokens = response_obj.usage.prompt_tokens + response_obj.usage.completion_tokens

    # Add missing attributes for OpenAI compatibility
    response_obj.usage.completion_tokens_details = None
    response_obj.usage.prompt_tokens_details = None

    return response_obj


def extract_sections_from_article(article_text: str, topic: str, base_path: str = None,
                                 source_id: str = None, token_tracker: TokenTracker = None,
                                 model_name: str = None, content_type: str = "basic_articles",
                                 variables_manager=None) -> List[Dict]:
    """Extracts structured prompt data from a single article text.

    Args:
        article_text: The text content to extract prompts from
        topic: The topic for context
        base_path: Path to save LLM interactions
        source_id: Identifier for the source
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
        content_type: Type of content (basic_articles, guides, etc.)
        variables_manager: Optional VariablesManager instance
    """
    logger.info("Extracting prompts from one article...")
    try:
        messages = _load_and_prepare_messages(
            content_type,
            "01_extract",
            {"topic": topic, "article_text": article_text},
            variables_manager=variables_manager,
            stage_name="extract_sections"
        )

        # Use unified LLM request system with post-processor for automatic retry/fallback
        from src.llm_request import make_llm_request
        parsed_result, actual_model = make_llm_request(
            stage_name="extract_sections",
            messages=messages,
            temperature=0.3,
            token_tracker=token_tracker,
            base_path=base_path,
            validation_level="minimal",  # Extract prompts uses minimal validation
            post_processor=_extract_post_processor  # ✅ Automatic retry/fallback on JSON parsing errors
        )

        # parsed_result is already a List[Dict] from post_processor
        # Сохраняем запрос и ответ для отладки
        if base_path:
            save_llm_interaction(
                base_path=base_path,
                stage_name="extract_sections",
                messages=messages,
                response=str(parsed_result),  # Convert to string for logging
                request_id=source_id or "single",
                extra_params={"response_format": "json_object", "topic": topic, "model": actual_model}
            )

        # Return parsed result directly (already List[Dict] from post_processor)
        return parsed_result if isinstance(parsed_result, list) else []

    except Exception as e:
        logger.error(f"Failed to extract prompts via API: {e}")
        return []






async def _generate_single_section_async(section: Dict, idx: int, topic: str,
                                        sections_path: str, model_name: str,
                                        token_tracker: TokenTracker, content_type: str = "basic_articles") -> Dict:
    """
    Generates a single section asynchronously with timeout protection.

    Retry/fallback logic is handled by the unified LLM request system:
    - 3 retry attempts on primary model
    - Automatic fallback to secondary model
    - 3 retry attempts on fallback model
    Total: 6 attempts with progressive backoff
    """
    section_num = f"section_{idx}"
    section_title = section.get('section_title', f'Section {idx}')

    # Prepare section path first
    section_path = None
    if sections_path:
        section_path = os.path.join(sections_path, section_num)
        os.makedirs(section_path, exist_ok=True)

    # Wait for HTTP request timing - each section waits (idx-1)*5 seconds
    if idx > 1:
        http_delay = (idx - 1) * 5
        logger.info(f"⏳ Section {idx} waiting {http_delay}s before HTTP request...")
        await asyncio.sleep(http_delay)
        logger.info(f"✅ Section {idx} finished waiting, starting HTTP request...")

    try:
        logger.info(f"🔄 Generating section {idx}: {section_title}")

        # Prepare section-specific prompt
        messages = _load_and_prepare_messages(
            content_type,
            "01_generate_section",
            {
                "topic": topic,
                "section_title": section.get("section_title", ""),
                "section_structure": json.dumps(section, indent=2, ensure_ascii=False)
            }
        )

        # Use timeout-aware request function (unified system handles all retry/fallback internally)
        response_obj, actual_model = await _make_llm_request_with_timeout(
            stage_name="generate_article",
            model_name=model_name,
            messages=messages,
            token_tracker=token_tracker,
            timeout=MODEL_TIMEOUT,
            base_path=section_path,
            temperature=0.3
        )

        section_content = response_obj.choices[0].message.content
        section_content = clean_llm_tokens(section_content)  # Очищаем токены LLM

        # Validation happens inside unified LLM request system (v3.0 validation)
        # No additional validation needed here

        # Save section interaction
        if section_path:
            save_llm_interaction(
                base_path=section_path,
                stage_name="generate_section",
                messages=messages,
                response=section_content,
                extra_params={
                    "topic": topic,
                    "section_num": idx,
                    "section_title": section.get("section_title", ""),
                    "model": actual_model
                }
            )

        logger.info(f"✅ Successfully generated section {idx}: {section_title}")

        result = {
            "section_num": idx,
            "section_title": section.get("section_title", ""),
            "content": section_content,
            "status": "success"
        }

        logger.info(f"🎯 Section {idx} COMPLETED and returning result")
        return result

    except Exception as e:
        logger.error(f"💥 Section {idx} failed after all retry/fallback attempts: {e}", exc_info=True)
        return {
            "section_num": idx,
            "section_title": section.get("section_title", ""),
            "content": f"<p>Не удалось сгенерировать раздел '{section_title}' после всех попыток. Ошибка: {str(e)}</p>",
            "status": "failed",
            "error": str(e)
        }


def generate_article_by_sections(structure: List[Dict], topic: str, base_path: str = None,
                                 token_tracker: TokenTracker = None, model_name: str = None,
                                 content_type: str = "basic_articles", variables_manager=None) -> Dict[str, Any]:
    """Generates WordPress article by processing sections SEQUENTIALLY without any async operations.

    Args:
        structure: Ultimate structure with sections to generate
        topic: The topic for the article
        base_path: Path to save LLM interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
        content_type: Type of content (basic_articles, guides, etc.)
        variables_manager: Optional VariablesManager instance

    Returns:
        Dict with raw_response containing merged sections and metadata
    """
    logger.info(f"Starting SEQUENTIAL section-by-section article generation for topic: {topic}")

    # Parse actual ultimate_structure format with SMART DETECTION
    actual_sections = []

    if isinstance(structure, dict) and "article_structure" in structure:
        # НОВЫЙ ПРАВИЛЬНЫЙ ФОРМАТ - объект ultimate_structure
        actual_sections = structure["article_structure"]
        logger.info(f"✅ Found {len(actual_sections)} sections in ultimate_structure object")
    elif isinstance(structure, list) and len(structure) > 0:
        if isinstance(structure[0], dict) and "article_structure" in structure[0]:
            # СТАРЫЙ ФОРМАТ - массив с объектом
            actual_sections = structure[0]["article_structure"]
            logger.info(f"Found {len(actual_sections)} sections in article_structure (legacy format)")
        else:
            # ПРЯМОЙ МАССИВ СЕКЦИЙ
            actual_sections = structure
            logger.info(f"Using raw structure with {len(actual_sections)} sections")
    else:
        logger.error(f"Invalid structure format: {type(structure)}")
        actual_sections = []

    if not actual_sections:
        logger.error("No sections found in structure")
        return {"raw_response": json.dumps({"error": "No sections in structure"}, ensure_ascii=False)}

    total_sections = len(actual_sections)
    logger.info(f"Extracted {total_sections} sections from article_structure")

    # Create sections directory
    sections_path = None
    if base_path:
        sections_path = os.path.join(base_path, "sections")
        os.makedirs(sections_path, exist_ok=True)

    # Generate sections SEQUENTIALLY with context accumulation
    generated_sections = []
    ready_sections = ""  # Накопитель контекста предыдущих разделов

    for idx, section in enumerate(actual_sections, 1):
        section_num = f"section_{idx}"
        section_title = section.get('section_title', f'Section {idx}')

        # Prepare section path first
        section_path = None
        if sections_path:
            section_path = os.path.join(sections_path, section_num)
            os.makedirs(section_path, exist_ok=True)

        # Prepare ready_sections context
        if idx == 1:
            ready_sections = "Это первый раздел статьи."
        else:
            # Накапливаем все предыдущие разделы ПОЛНОСТЬЮ
            ready_sections_parts = []
            for prev_section in generated_sections:
                if prev_section.get("status") == "success" and prev_section.get("content"):
                    prev_title = prev_section.get("section_title", f"Раздел {prev_section.get('section_num', '')}")
                    prev_content = prev_section.get("content", "")
                    ready_sections_parts.append(f"РАЗДЕЛ: {prev_title}\n{prev_content}")

            ready_sections = "\n\n".join(ready_sections_parts) if ready_sections_parts else "Предыдущие разделы недоступны."

        # No outer retry loop - make_llm_request() handles all retries internally (6 attempts total)
        try:
            # Prepare section-specific prompt with ready_sections context
            messages = _load_and_prepare_messages(
                content_type,
                "01_generate_section",
                {
                    "topic": topic,
                    "section_title": section.get("section_title", ""),
                    "section_structure": json.dumps(section, indent=2, ensure_ascii=False),
                    "ready_sections": ready_sections
                },
                variables_manager=variables_manager,
                stage_name="generate_article"
            )

            # Use unified LLM request with automatic retry/fallback (6 attempts internally)
            from src.llm_request import make_llm_request

            # Check if llm_model override is specified via variables_manager
            override_model = variables_manager.active_variables.get("llm_model") if variables_manager else None

            response_obj, actual_model = make_llm_request(
                stage_name="generate_article",
                model_name=override_model,  # Override model if specified
                messages=messages,
                temperature=0.3,
                token_tracker=token_tracker,
                base_path=section_path,
                validation_level="v3"  # Generate article uses v3.0 validation
            )

            section_content = response_obj.choices[0].message.content
            section_content = clean_llm_tokens(section_content)  # Очищаем токены LLM

            # Validation happens inside make_llm_request with retry/fallback (min_length=300)
            # No additional validation needed here

            # Save section interaction
            if section_path:
                save_llm_interaction(
                    base_path=section_path,
                    stage_name="generate_section",
                    messages=messages,
                    response=section_content,
                    extra_params={
                        "topic": topic,
                        "section_num": idx,
                        "section_title": section.get("section_title", ""),
                        "model": actual_model
                    }
                )

            # Compact success log
            char_count = len(section_content)
            logger.info(f"Section {idx}/{total_sections}: {section_title}... ✅ ({char_count} chars)")

            result = {
                "section_num": idx,
                "section_title": section.get("section_title", ""),
                "content": section_content,
                "status": "success"
            }

            generated_sections.append(result)

        except Exception as e:
            logger.error(f"❌ Section {idx} failed after all retry attempts: {e}")
            result = {
                "section_num": idx,
                "section_title": section.get("section_title", ""),
                "content": f"<p>Не удалось сгенерировать раздел '{section_title}'. Ошибка: {str(e)}</p>",
                "status": "failed",
                "error": str(e)
            }
            generated_sections.append(result)

    # Report generation status
    successful_sections = [s for s in generated_sections if s["status"] == "success"]
    failed_sections = [s for s in generated_sections if s["status"] == "failed"]

    logger.info("=" * 60)
    logger.info("📊 SECTION GENERATION REPORT:")
    logger.info(f"✅ Completed: {len(successful_sections)}/{total_sections} sections")
    if failed_sections:
        logger.warning(f"❌ Failed: {len(failed_sections)} sections")
        for failed in failed_sections:
            logger.warning(f"  - Section {failed['section_num']}: {failed.get('error', 'Unknown error')}")
    logger.info(f"📈 Success rate: {len(successful_sections)/total_sections*100:.1f}%")
    logger.info("=" * 60)

    # Merge all sections
    merged_content = merge_sections(generated_sections, topic, structure)

    # Save merged content
    if base_path:
        with open(os.path.join(base_path, "merged_content.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "sections": generated_sections,
                "merged": merged_content
            }, f, indent=2, ensure_ascii=False)

        # Save HTML version of merged content
        with open(os.path.join(base_path, "article_content.html"), 'w', encoding='utf-8') as f:
            f.write(merged_content.get("content", ""))

    logger.info(f"🎉 Article generation COMPLETE: {len(successful_sections)}/{total_sections} sections generated successfully")

    return {
        "raw_response": json.dumps(merged_content, ensure_ascii=False),
        "topic": topic,
        "generated_sections": generated_sections  # Add sections for fact-checking
    }


def generate_article_by_sections_OLD_ASYNC(structure: List[Dict], topic: str, base_path: str = None,
                                 token_tracker: TokenTracker = None, model_name: str = None, content_type: str = "basic_articles") -> Dict[str, Any]:
    """Generates WordPress article by processing sections in parallel with staggered starts.

    Args:
        structure: Ultimate structure with sections to generate
        topic: The topic for the article
        base_path: Path to save LLM interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)

    Returns:
        Dict with raw_response containing merged sections and metadata
    """
    logger.info(f"Starting PARALLEL section-by-section article generation for topic: {topic}")

    # ИСПРАВЛЕНИЕ: парсим реальный формат ultimate_structure с SMART DETECTION
    actual_sections = []

    if isinstance(structure, dict) and "article_structure" in structure:
        # НОВЫЙ ПРАВИЛЬНЫЙ ФОРМАТ - объект ultimate_structure
        actual_sections = structure["article_structure"]
        logger.info(f"✅ Extracted {len(actual_sections)} sections from ultimate_structure object")
    elif isinstance(structure, list) and len(structure) > 0:
        if isinstance(structure[0], dict) and "article_structure" in structure[0]:
            # Формат: [{"article_structure": [секции...]}]
            actual_sections = structure[0]["article_structure"]
            logger.info(f"Extracted {len(actual_sections)} sections from article_structure (legacy format)")
        else:
            # Формат: [секции...]
            actual_sections = structure
    else:
        logger.error("Invalid structure provided for section generation")
        return {"raw_response": "ERROR: Invalid structure", "topic": topic}

    if not actual_sections:
        logger.error("No sections found in structure")
        return {"raw_response": "ERROR: No sections found", "topic": topic}

    # Create sections subdirectory
    sections_path = os.path.join(base_path, "sections") if base_path else None
    if sections_path:
        os.makedirs(sections_path, exist_ok=True)

    total_sections = len(actual_sections)

    async def run_parallel_generation():
        """Run section generation with staggered HTTP requests"""
        tasks = []

        # Start all tasks immediately - delays will be inside each task
        for idx, section in enumerate(actual_sections, 1):
            section_title = section.get('section_title', f'Section {idx}')
            logger.info(f"🚀 Starting section {idx}/{total_sections}: {section_title}")

            # Create task - HTTP delay will be handled inside the function
            coro = _generate_single_section_async(
                section=section,
                idx=idx,
                topic=topic,
                sections_path=sections_path,
                model_name=model_name,
                token_tracker=token_tracker
            )

            # Convert coroutine to task for asyncio.wait()
            task = asyncio.create_task(coro)
            tasks.append(task)

        logger.info(f"🔥 All {total_sections} sections started! HTTP requests will be staggered by 5 seconds each...")

        # Wait for tasks to complete with 10-minute timeout and real-time progress tracking
        timeout_seconds = 10 * 60  # 10 minutes
        logger.info(f"⏳ Waiting for sections to complete (timeout: {timeout_seconds//60} minutes)...")

        # Track progress with asyncio.wait and periodic checking
        completed_sections = 0
        start_time = time.time()

        # Use asyncio.wait with shorter timeout for progress updates
        remaining_tasks = set(tasks)
        all_results = []

        while remaining_tasks and (time.time() - start_time) < timeout_seconds:
            # Wait for any task to complete, with 30-second intervals for progress updates
            done, pending = await asyncio.wait(
                remaining_tasks,
                timeout=30,  # Check progress every 30 seconds
                return_when=asyncio.FIRST_COMPLETED
            )

            # Process newly completed tasks
            for task in done:
                completed_sections += 1
                elapsed = time.time() - start_time
                logger.info(f"📈 Progress: {completed_sections}/{total_sections} sections completed ({elapsed:.1f}s elapsed)")
                remaining_tasks.discard(task)
                all_results.append(task)

            # Update remaining tasks
            remaining_tasks = pending

            # Log progress if tasks are still running
            if remaining_tasks and completed_sections < total_sections:
                elapsed = time.time() - start_time
                remaining_count = len(remaining_tasks)
                logger.info(f"⏳ Still waiting: {remaining_count}/{total_sections} sections pending ({elapsed:.1f}s elapsed)")

        # Final state
        elapsed_time = time.time() - start_time
        done = set(all_results)
        pending = remaining_tasks

        completed_count = len(done)
        pending_count = len(pending)

        if pending_count > 0:
            logger.warning(f"⏰ TIMEOUT: {completed_count}/{total_sections} sections completed in {timeout_seconds//60} minutes")
            logger.warning(f"❌ {pending_count} sections still pending - proceeding with partial results")
        else:
            logger.info(f"🎉 All {total_sections} sections completed successfully!")

        # Process completed results
        generated_sections = []
        completed_results = []
        failed_sections = []
        pending_sections = []

        # Get results from completed tasks
        for task in done:
            try:
                result = await task
                if isinstance(result, Exception):
                    raise result
                completed_results.append(result)
                generated_sections.append(result)
                logger.info(f"✅ Section {result.get('section_num', '?')} completed successfully")
            except Exception as e:
                # Find which section this task was for
                task_index = tasks.index(task) if task in tasks else -1
                section_num = task_index + 1
                section_title = actual_sections[task_index].get("section_title", f"Section {section_num}") if task_index >= 0 else "Unknown"

                logger.error(f"❌ Section {section_num} failed: {e}")
                failed_sections.append({"section_num": section_num, "section_title": section_title, "error": str(e)})
                generated_sections.append({
                    "section_num": section_num,
                    "section_title": section_title,
                    "content": "",
                    "status": "failed",
                    "error": str(e)
                })

        # Handle pending (timed out) tasks
        for task in pending:
            task_index = tasks.index(task) if task in tasks else -1
            section_num = task_index + 1
            section_title = actual_sections[task_index].get("section_title", f"Section {section_num}") if task_index >= 0 else "Unknown"

            logger.warning(f"⏰ Section {section_num} timed out - still processing")
            pending_sections.append({"section_num": section_num, "section_title": section_title})
            generated_sections.append({
                "section_num": section_num,
                "section_title": section_title,
                "content": "",
                "status": "timeout",
                "error": "Timed out after 10 minutes"
            })

        # Generate detailed report
        successful_count = len(completed_results)
        failed_count = len(failed_sections)
        timeout_count = len(pending_sections)

        logger.info("=" * 60)
        logger.info("📊 SECTION GENERATION REPORT:")
        logger.info(f"✅ Completed: {successful_count}/{total_sections} sections")
        if failed_sections:
            failed_nums = [str(s["section_num"]) for s in failed_sections]
            logger.warning(f"❌ Failed: sections {', '.join(failed_nums)}")
            for failed in failed_sections:
                logger.warning(f"   Section {failed['section_num']}: {failed['error']}")
        if pending_sections:
            pending_nums = [str(s["section_num"]) for s in pending_sections]
            logger.warning(f"⏰ Timed out: sections {', '.join(pending_nums)}")
        logger.info(f"📈 Success rate: {(successful_count/total_sections)*100:.1f}%")
        logger.info(f"⏱️ Total processing time: {elapsed_time:.1f}s ({elapsed_time/60:.1f} minutes)")
        if elapsed_time >= timeout_seconds:
            logger.warning(f"⚠️ Process hit the {timeout_seconds//60}-minute timeout limit")
        logger.info("=" * 60)

        return generated_sections

    # Run the async generation with improved event loop handling
    import asyncio
    try:
        # Check if we're already in an async context
        loop = asyncio.get_running_loop()
        # If we're already in an async context, use nest_asyncio carefully
        import nest_asyncio
        nest_asyncio.apply()
        logger.info("🔄 Using existing event loop with nest_asyncio for section generation")

        # Create a new task to ensure proper completion
        task = loop.create_task(run_parallel_generation())
        generated_sections = loop.run_until_complete(task)

    except RuntimeError:
        # No event loop running, create a new one
        logger.info("🔄 Creating new event loop for section generation")
        generated_sections = asyncio.run(run_parallel_generation())

    # Merge all sections
    merged_content = merge_sections(generated_sections, topic, structure)

    # Save merged content
    if base_path:
        with open(os.path.join(base_path, "merged_content.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "sections": generated_sections,
                "merged": merged_content
            }, f, indent=2, ensure_ascii=False)

        # Save HTML version of merged content
        with open(os.path.join(base_path, "article_content.html"), 'w', encoding='utf-8') as f:
            f.write(merged_content.get("content", ""))

    successful_sections = [s for s in generated_sections if s["status"] == "success"]
    logger.info(f"🎉 Article generation FULLY COMPLETE: {len(successful_sections)}/{total_sections} sections generated successfully")
    logger.info(f"📋 All async tasks have finished, proceeding to merge sections...")

    return {
        "raw_response": json.dumps(merged_content, ensure_ascii=False),
        "topic": topic,
        "generated_sections": generated_sections  # Add sections for fact-checking
    }


def _convert_markdown_to_html(markdown_content: str) -> str:
    """Converts markdown content to HTML suitable for WordPress.

    Args:
        markdown_content: Raw markdown text from section generation

    Returns:
        Clean HTML content
    """
    if not markdown_content:
        return ""

    content = markdown_content.strip()

    # Convert code blocks using placeholder approach
    code_blocks = []
    def extract_code_block(match):
        language = match.group(1) if match.group(1) else ''
        code_content = match.group(2)
        if language:
            html_code = f"<pre><code class='language-{language}'>{code_content}</code></pre>"
        else:
            html_code = f"<pre><code>{code_content}</code></pre>"
        placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
        code_blocks.append(html_code)
        return placeholder

    # Extract code blocks first
    content = re.sub(r'```(\w+)?\n(.*?)\n```', extract_code_block, content, flags=re.DOTALL)

    # Convert markdown headers
    content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
    content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
    content = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', content, flags=re.MULTILINE)
    content = re.sub(r'^##### (.+)$', r'<h5>\1</h5>', content, flags=re.MULTILINE)

    # Convert bold text
    content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
    content = re.sub(r'__(.+?)__', r'<strong>\1</strong>', content)

    # Convert italic text
    content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
    content = re.sub(r'_(.+?)_', r'<em>\1</em>', content)

    # Convert inline code
    content = re.sub(r'`(.+?)`', r'<code>\1</code>', content)

    # Convert links
    content = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', content)

    # Convert unordered lists
    lines = content.split('\n')
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            item_content = stripped[2:].strip()
            html_lines.append(f'<li>{item_content}</li>')
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False

            # Convert empty lines to paragraph breaks
            if not stripped:
                html_lines.append('<br>')
            else:
                # Wrap non-header content in paragraphs
                if not (stripped.startswith('<h') or stripped.startswith('<ul') or
                       stripped.startswith('<li') or stripped.startswith('<br') or
                       stripped.startswith('<pre') or '</pre>' in stripped):
                    html_lines.append(f'<p>{stripped}</p>')
                else:
                    html_lines.append(stripped)

    # Close any open list
    if in_list:
        html_lines.append('</ul>')

    result = '\n'.join(html_lines)

    # Clean up multiple breaks and empty paragraphs
    result = re.sub(r'<br>\s*<br>', '<br>', result)
    result = re.sub(r'<p></p>', '', result)
    result = re.sub(r'<p>\s*</p>', '', result)

    return result


def group_sections_for_fact_check(sections: List[Dict], group_size: int = 3) -> List[List[Dict]]:
    """
    Группирует секции для батчевой обработки факт-чека.

    Args:
        sections: Список секций для группировки
        group_size: Размер группы (по умолчанию 3)

    Returns:
        Список групп секций

    Example:
        8 секций → [[1,2,3], [4,5,6], [7,8]]
        5 секций → [[1,2,3], [4,5]]
        2 секции → [[1,2]]
    """
    groups = []
    for i in range(0, len(sections), group_size):
        group = sections[i:i + group_size]
        groups.append(group)

    logger.info(f"Grouped {len(sections)} sections into {len(groups)} groups of max {group_size} sections each")
    return groups


def fact_check_sections(sections: List[Dict], topic: str, base_path: str = None,
                       token_tracker: TokenTracker = None, model_name: str = None,
                       content_type: str = "basic_articles", variables_manager=None) -> tuple:
    """
    Performs fact-checking on groups of sections and returns combined content with status.

    Args:
        sections: List of generated sections with content
        topic: Article topic
        base_path: Path to save fact-check interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
        content_type: Content type for prompt selection

    Returns:
        Tuple: (combined_fact_checked_content, fact_check_status)
    """
    logger.info(f"Starting grouped fact-checking for {len(sections)} sections...")

    # Filter successful sections (accept both "success" and "translated" statuses)
    successful_sections = [s for s in sections if s.get("status") in ["success", "translated"] and s.get("content")]

    # Initialize fact-check status tracking
    fact_check_status = {
        "success": False,
        "total_groups": 0,
        "failed_groups": 0,
        "failed_sections": [],
        "error_details": []
    }

    if not successful_sections:
        logger.warning("No successful sections to fact-check")
        fact_check_status["success"] = True  # Nothing to check = success
        # Return combined content of original sections
        combined_content = "\n\n".join([s.get("content", "") for s in sections if s.get("content")])
        return combined_content, fact_check_status

    total_sections = len(successful_sections)
    logger.info(f"Total successful sections: {total_sections}")

    # Group sections by 3
    section_groups = group_sections_for_fact_check(successful_sections, group_size=3)
    logger.info(f"Created {len(section_groups)} groups for fact-checking")

    # Update status with total groups
    fact_check_status["total_groups"] = len(section_groups)

    fact_checked_content_parts = []

    # Process each group
    for group_idx, group in enumerate(section_groups):
        group_num = group_idx + 1
        logger.info(f"🔍 Fact-checking group {group_num}/{len(section_groups)} with {len(group)} sections")

        # No outer retry loop - make_llm_request() handles all retries internally (6 attempts total)
        try:

            # Combine content from all sections in the group
            combined_content = ""
            section_titles = []

            for section in group:
                section_title = section.get("section_title", "Untitled Section")
                section_content = section.get("content", "")
                section_titles.append(section_title)
                combined_content += f"<h2>{section_title}</h2>\n{section_content}\n\n"

            # Prepare messages for fact-checking the group
            messages = _load_and_prepare_messages(
                content_type,
                "10_fact_check",
                {
                    "topic": topic,
                    "section_title": f"Группа {group_num} ({', '.join(section_titles)})",
                    "section_content": combined_content.strip()
                },
                variables_manager=variables_manager,
                stage_name="fact_check"
            )

            # Create group-specific path
            group_path = os.path.join(base_path, f"group_{group_num}") if base_path else None

            # Make fact-check request with automatic retry/fallback (6 attempts internally)
            response_obj, actual_model = make_llm_request(
                stage_name="fact_check",
                model_name=model_name or LLM_MODELS.get("fact_check"),
                messages=messages,
                token_tracker=token_tracker,
                base_path=group_path,
                temperature=0.2,  # Low temperature for factual accuracy
                validation_level="minimal"  # Fact-check uses minimal validation (doc: short factual answers)
            )

            fact_checked_content = response_obj.choices[0].message.content
            fact_checked_content = clean_llm_tokens(fact_checked_content)  # Очищаем токены LLM

            # DEBUG: Log content size immediately after extraction
            logger.info(f"🔍 FACT_CHECK EXTRACTED CONTENT: {len(fact_checked_content)} chars")

            # Debug logging to track content size
            logger.info(f"📊 Group {group_num} - Response content size: {len(fact_checked_content)} chars")
            logger.info(f"📊 Group {group_num} - First 100 chars: {fact_checked_content[:100]}...")
            logger.info(f"📊 Group {group_num} - Last 100 chars: ...{fact_checked_content[-100:]}")

            # Save interaction
            if group_path:
                save_llm_interaction(
                    base_path=group_path,
                    stage_name="fact_check",
                    messages=messages,
                    response=fact_checked_content,
                    request_id=f"group_{group_num}_fact_check",
                    extra_params={"model": actual_model}
                )

            fact_checked_content_parts.append(fact_checked_content)
            logger.info(f"✅ Group {group_num} fact-checked successfully")

            # Add delay between group fact-check requests to avoid rate limits
            if group_idx < len(section_groups) - 1:
                delay = 3  # 3 seconds between group requests
                logger.info(f"⏳ Waiting {delay}s before next group fact-check...")
                time.sleep(delay)

        except Exception as e:
            # All retry attempts exhausted in make_llm_request
            logger.error(f"💥 Group {group_num} fact-check failed after all retry attempts: {e}")

            # Track failure in status
            fact_check_status["failed_groups"] += 1
            group_section_titles = [section.get("section_title", "Untitled Section") for section in group]
            fact_check_status["failed_sections"].extend(group_section_titles)
            fact_check_status["error_details"].append({
                "group": group_num,
                "sections": group_section_titles,
                "error": str(e)
            })

            # Keep original content for this group if fact-check fails
            group_original_content = ""
            for section in group:
                section_title = section.get("section_title", "Untitled Section")
                section_content = section.get("content", "")
                group_original_content += f"<h2>{section_title}</h2>\n{section_content}\n\n"
            fact_checked_content_parts.append(group_original_content.strip())

    # Combine all fact-checked content parts
    combined_fact_checked_content = "\n\n".join(fact_checked_content_parts)

    # Finalize status
    fact_check_status["success"] = (fact_check_status["failed_groups"] == 0)

    # Log final status
    if fact_check_status["success"]:
        logger.info(f"✅ Fact-checking completed successfully: {len(section_groups)} groups processed")
    else:
        logger.warning(f"⚠️ Fact-checking partially failed: {fact_check_status['failed_groups']}/{fact_check_status['total_groups']} groups failed")
        logger.warning(f"Failed sections: {', '.join(fact_check_status['failed_sections'])}")

    logger.info(f"Combined content length: {len(combined_fact_checked_content)} chars")

    return combined_fact_checked_content, fact_check_status


def merge_sections(sections: List[Dict], topic: str, structure: List[Dict]) -> Dict[str, Any]:
    """Merges individual sections into a complete WordPress article.

    Args:
        sections: List of generated sections with content
        topic: Article topic
        structure: Original structure for reference

    Returns:
        WordPress-ready article structure
    """
    logger.info("Merging sections into complete article...")

    # Filter successful sections (including fact-checked and skipped)
    successful_sections = [s for s in sections if s.get("status") in ["success", "fact_checked", "fact_check_skipped"] and s.get("content")]

    if not successful_sections:
        logger.error("No successful sections to merge")
        return {
            "title": f"Ошибка генерации статьи по теме: {topic}",
            "content": "<p>К сожалению, не удалось сгенерировать контент для этой статьи.</p>",
            "excerpt": "Ошибка генерации",
            "error": "No sections generated successfully"
        }

    # Combine section contents with proper markdown to HTML conversion
    combined_html_content = []

    for section in successful_sections:
        content = section.get("content", "").strip()
        if content:
            # Convert markdown to HTML
            html_content = _convert_markdown_to_html(content)
            combined_html_content.append(html_content)

    # Join all sections with proper spacing
    final_content = "\n\n".join(combined_html_content)

    # Generate title and metadata
    title = f"Полное руководство: {topic}"
    excerpt = f"Подробное руководство по теме {topic} с практическими примерами и рекомендациями экспертов."

    # Create slug
    slug = topic.lower().replace(" ", "-")
    slug = re.sub(r'[^\w\-]', '', slug)[:50]

    # Build WordPress structure
    wordpress_data = {
        "title": title,
        "content": final_content,
        "excerpt": excerpt,
        "slug": slug,
        "categories": ["articles"],
        "_yoast_wpseo_title": title[:60],
        "_yoast_wpseo_metadesc": excerpt[:160],
        "focus_keyword": topic.split()[0] if topic else "guide",
        "sections_generated": len(successful_sections),
        "sections_total": len(sections)
    }

    logger.info(f"Merged {len(successful_sections)} sections into article")

    return wordpress_data


def editorial_review(raw_response: str, topic: str, base_path: str = None,
                    token_tracker: TokenTracker = None, model_name: str = None,
                    content_type: str = "basic_articles", variables_manager=None) -> Dict[str, Any]:
    """
    Performs editorial review and cleanup of WordPress article data with advanced retry and fallback logic.

    Args:
        raw_response: Raw response string from generate_wordpress_article()
        topic: The topic for the article (used in editorial prompt)
        base_path: Path to save LLM interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
        content_type: Type of content (basic_articles, guides, etc.)
        variables_manager: Optional VariablesManager instance
    """
    logger.info("🔧 Starting editorial review with advanced retry logic...")
    
    # Check for error responses
    if raw_response.startswith("ERROR:"):
        logger.error(f"Received error from previous stage: {raw_response}")
        return _create_error_response(topic, f"Ошибка на предыдущем этапе: {raw_response}", "generation-error")
    
    # Prepare messages
    try:
        messages = _load_and_prepare_messages(
            content_type,
            "02_editorial_review",
            {
                "raw_response": raw_response,
                "topic": topic
                # article_length is provided by variables_manager if set via CLI
            },
            variables_manager=variables_manager,
            stage_name="editorial_review"
        )
    except Exception as e:
        logger.error(f"Failed to load editorial review prompt: {e}")
        return _create_error_response(topic, f"Ошибка загрузки промпта: {str(e)}", "prompt-error")

    # Use unified LLM request with automatic fallback AND post-processing
    try:
        from src.llm_request import make_llm_request

        # Check if llm_model override is specified via variables_manager
        override_model = variables_manager.active_variables.get("llm_model") if variables_manager else None

        # Call make_llm_request with post_processor for automatic retry/fallback on JSON parsing errors
        parsed_result, actual_model = make_llm_request(
            stage_name="editorial_review",
            model_name=override_model,  # Override model if specified
            messages=messages,
            temperature=0.2,
            # NO response_format - let model return raw JSON, parse with normalization
            token_tracker=token_tracker,
            base_path=base_path,
            validation_level="minimal",  # Editorial uses minimal validation (doc: content already validated on stages 8+9)
            post_processor=_editorial_post_processor  # ✅ Automatic retry/fallback on JSON parsing errors
        )

        # Save interaction (post-processor already parsed and cleaned)
        if base_path:
            save_llm_interaction(
                base_path=base_path,
                stage_name="editorial_review",
                messages=messages,
                response=json.dumps(parsed_result, ensure_ascii=False, indent=2),
                request_id="editorial_review",
                extra_params={
                    "topic": topic,
                    "model": actual_model
                }
            )

        logger.info(f"✅ Editorial review SUCCESS with {actual_model}")
        logger.info(f"📄 Article title: {parsed_result.get('title', 'No title')}")
        return parsed_result

    except Exception as e:
        logger.error(f"🚨 Editorial review failed after all retries and fallback: {e}", exc_info=True)
        return _create_error_response(
            topic,
            "Не удалось выполнить редакторскую правку после всех попыток с основной и резервной моделями",
            "editorial-failure"
        )


def _repair_json_control_chars(text: str) -> str:
    """
    Universal JSON repair: escapes control characters ONLY within string values.

    Uses state machine to track context (inside/outside JSON strings).

    Handles:
    - Unescaped newlines, tabs, carriage returns in string values
    - Preserves legitimate newlines between JSON fields
    - Doesn't double-escape already-escaped sequences
    - Works with any broken JSON from any LLM model

    Args:
        text: Potentially broken JSON string

    Returns:
        Repaired JSON string with properly escaped control characters
    """
    result = []
    i = 0
    in_string = False

    while i < len(text):
        char = text[i]

        # Preserve already-escaped sequences (e.g., \n, \", \\)
        if char == '\\' and i + 1 < len(text):
            result.append(char)
            result.append(text[i + 1])
            i += 2
            continue

        # Track string boundaries with double quotes
        if char == '"':
            in_string = not in_string
            result.append(char)
            i += 1
            continue

        # Escape control chars ONLY when inside a string value
        if in_string and ord(char) < 32:
            if char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            else:
                # Other control chars - use unicode escape
                result.append(f'\\u{ord(char):04x}')
        else:
            # Outside strings or not a control char - keep as-is
            result.append(char)

        i += 1

    return ''.join(result)


def _try_parse_editorial_json(response: str, model_name: str, attempt: int, model_label: str) -> Dict[str, Any]:
    """
    Attempts to parse JSON from editorial review response with enhanced normalization.

    Returns:
        Parsed JSON dict if successful, None if failed
    """
    logger.info(f"🔍 Parsing JSON from {model_label} model (attempt {attempt})...")
    import re

    # Attempt 0: Universal repair (markdown + control chars)
    try:
        logger.info("🛠️ Attempt 0: Universal JSON repair...")
        cleaned_response = response.strip()

        # Step 1: Remove everything BEFORE first { and AFTER last }
        cleaned_response = re.sub(r'^.*?({)', r'\1', cleaned_response, flags=re.DOTALL)
        cleaned_response = re.sub(r'(})[^}]*$', r'\1', cleaned_response, flags=re.DOTALL)
        logger.debug(f"After markdown removal: {len(cleaned_response)} chars")

        # Step 2: Repair control characters (universal state-machine approach)
        repaired_response = _repair_json_control_chars(cleaned_response)
        logger.debug(f"After control char repair: {len(repaired_response)} chars")
        logger.debug(f"First 200 chars: {repaired_response[:200]}")

        parsed = json.loads(repaired_response)
        logger.info("✅ Attempt 0: Universal repair successful")
        return parsed

    except json.JSONDecodeError as e:
        logger.info(f"❌ Attempt 0 failed: {e}")

    # Attempt 1: Direct parsing with basic cleanup
    try:
        logger.info("🛠️ Attempt 1: Direct parsing with basic cleanup...")
        cleaned_response = response.strip()

        # Special handling for Gemini models
        if "gemini" in model_name.lower():
            logger.info("🧹 Applying Gemini-specific cleanup...")
            if cleaned_response.startswith('```'):
                first_newline = cleaned_response.find('\n')
                if first_newline > 0:
                    cleaned_response = cleaned_response[first_newline+1:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
        else:
            # Standard cleanup with regex to handle newlines
            cleaned_response = re.sub(r'^```json\s*', '', cleaned_response)
            cleaned_response = re.sub(r'\s*```$', '', cleaned_response)

        cleaned_response = cleaned_response.strip()
        logger.debug(f"After basic cleanup: {len(cleaned_response)} chars")

        parsed = json.loads(cleaned_response)
        logger.info("✅ Direct JSON parsing successful")
        return parsed

    except json.JSONDecodeError as e:
        logger.info(f"❌ Attempt 1 failed: {e}")

    # Attempts 2-4: Enhanced normalization
    for cleanup_attempt in range(2, 5):
        logger.info(f"🛠️ Attempt {cleanup_attempt}: Enhanced normalization...")

        try:
            if cleanup_attempt == 2:
                # Fix common escaping issues
                fixed_response = response.strip()
                fixed_response = re.sub(r'\\\\"', '"', fixed_response)
                fixed_response = re.sub(r'class="([^"]*)"', r"class='\1'", fixed_response)
                fixed_response = re.sub(r'language-([^"]*)"', r"language-\1'", fixed_response)
                logger.debug(f"After escaping fixes: {len(fixed_response)} chars")

            elif cleanup_attempt == 3:
                # Extract JSON block with regex
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if not json_match:
                    logger.info("❌ No JSON block found with regex")
                    continue
                fixed_response = json_match.group(0)
                logger.debug(f"After regex extraction: {len(fixed_response)} chars")
                logger.debug(f"First 200 chars: {fixed_response[:200]}")

            elif cleanup_attempt == 4:
                # Fix incomplete JSON
                fixed_response = response.strip()
                brace_count = fixed_response.count('{') - fixed_response.count('}')
                if brace_count > 0:
                    fixed_response += '}' * brace_count
                    logger.debug(f"Added {brace_count} closing braces")
                logger.debug(f"After brace fix: {len(fixed_response)} chars")

            # Try parsing
            parsed = json.loads(fixed_response)
            logger.info(f"✅ Attempt {cleanup_attempt} successful")
            return parsed

        except json.JSONDecodeError as e:
            logger.info(f"❌ Attempt {cleanup_attempt} failed: {e}")
            continue

    # All normalization attempts failed
    logger.error("💥 All JSON normalization attempts failed")
    logger.error(f"Response length: {len(response)} characters")
    logger.error(f"First 300 chars: {response[:300]}")
    logger.error(f"Last 300 chars: {response[-300:]}")

    return None


def _create_error_response(topic: str, error_message: str, error_type: str) -> Dict[str, Any]:
    """Creates a standardized error response for editorial review failures."""
    return {
        "title": f"Ошибка обработки: {topic}",
        "content": f"<p>{error_message}</p>",
        "excerpt": "Ошибка при обработке статьи",
        "slug": error_type,
        "categories": ["prompts"],
        "_yoast_wpseo_title": "Ошибка обработки",
        "_yoast_wpseo_metadesc": error_message[:150],
        "image_caption": "Ошибка",
        "focus_keyword": "ошибка"
    }


def place_links_in_sections(sections: List[Dict], topic: str, base_path: str = None,
                           token_tracker: TokenTracker = None, model_name: str = None,
                           content_type: str = "basic_articles", variables_manager=None) -> tuple:
    """
    Places relevant links in sections after fact-checking.
    Groups sections by 3 for batch processing.

    Args:
        sections: List of fact-checked sections with content
        topic: Article topic
        base_path: Path to save link-placement interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
        content_type: Content type for prompt selection
        variables_manager: Optional VariablesManager instance

    Returns:
        Tuple: (combined_content_with_links, link_placement_status)
    """
    logger.info(f"Starting link placement for {len(sections)} sections...")

    # Filter successful sections (accept both "success" and "translated" statuses)
    successful_sections = [s for s in sections if s.get("status") in ["success", "translated"] and s.get("content")]

    # Initialize link placement status tracking
    link_placement_status = {
        "success": False,
        "total_groups": 0,
        "failed_groups": 0,
        "failed_sections": [],
        "error_details": []
    }

    if not successful_sections:
        logger.warning("No successful sections for link placement")
        link_placement_status["success"] = True  # Nothing to process = success
        # Return combined content of original sections
        combined_content = "\n\n".join([s.get("content", "") for s in sections if s.get("content")])
        return combined_content, link_placement_status

    total_sections = len(successful_sections)
    logger.info(f"Total successful sections: {total_sections}")

    # Group sections by 3
    section_groups = group_sections_for_fact_check(successful_sections, group_size=3)
    logger.info(f"Created {len(section_groups)} groups for link placement")

    # Update status with total groups
    link_placement_status["total_groups"] = len(section_groups)

    content_with_links_parts = []

    # Process each group
    for group_idx, group in enumerate(section_groups):
        group_num = group_idx + 1
        logger.info(f"🔗 Placing links in group {group_num}/{len(section_groups)} with {len(group)} sections")

        # No outer retry loop - make_llm_request() handles all retries internally (6 attempts total)
        try:
            # Combine content from all sections in the group
            combined_content = ""
            section_titles = []

            for section in group:
                section_title = section.get("section_title", "Untitled Section")
                section_content = section.get("content", "")
                section_titles.append(section_title)
                combined_content += f"<h2>{section_title}</h2>\n{section_content}\n\n"

            # Prepare messages for link placement in the group
            messages = _load_and_prepare_messages(
                content_type,
                "11_link_placement",
                {
                    "topic": topic,
                    "section_title": f"Группа {group_num} ({', '.join(section_titles)})",
                    "section_content": combined_content.strip()
                },
                variables_manager=variables_manager,
                stage_name="link_placement"
            )

            # Create group-specific path
            group_path = os.path.join(base_path, f"group_{group_num}") if base_path else None

            # Make link placement request with automatic retry/fallback (6 attempts internally)
            response_obj, actual_model = make_llm_request(
                stage_name="link_placement",
                model_name=model_name or LLM_MODELS.get("link_placement"),
                messages=messages,
                token_tracker=token_tracker,
                base_path=group_path,
                temperature=0.3,  # Slightly higher for creative link placement
                validation_level="minimal"  # Link placement uses minimal validation (doc: HTML content causes false positives)
            )

            content_with_links = response_obj.choices[0].message.content
            content_with_links = clean_llm_tokens(content_with_links)  # Clean LLM tokens

            # Debug logging
            logger.info(f"📊 Group {group_num} - Response content size: {len(content_with_links)} chars")

            # Save interaction
            if group_path:
                save_llm_interaction(
                    base_path=group_path,
                    stage_name="link_placement",
                    messages=messages,
                    response=content_with_links,
                    request_id=f"group_{group_num}_link_placement",
                    extra_params={"model": actual_model}
                )

            content_with_links_parts.append(content_with_links)
            logger.info(f"✅ Group {group_num} link placement completed successfully")

            # Add delay between group requests to avoid rate limits
            if group_idx < len(section_groups) - 1:
                delay = 3  # 3 seconds between group requests
                logger.info(f"⏳ Waiting {delay}s before next group...")
                time.sleep(delay)

        except Exception as e:
            # All retry attempts exhausted in make_llm_request
            logger.error(f"💥 Group {group_num} link placement failed after all retry attempts: {e}")

            # Track failure in status
            link_placement_status["failed_groups"] += 1
            group_section_titles = [section.get("section_title", "Untitled Section") for section in group]
            link_placement_status["failed_sections"].extend(group_section_titles)
            link_placement_status["error_details"].append({
                "group": group_num,
                "sections": group_section_titles,
                "error": str(e)
            })

            # Keep original content for this group if link placement fails
            group_original_content = ""
            for section in group:
                section_title = section.get("section_title", "Untitled Section")
                section_content = section.get("content", "")
                group_original_content += f"<h2>{section_title}</h2>\n{section_content}\n\n"
            content_with_links_parts.append(group_original_content.strip())

    # Combine all content parts with links
    combined_content_with_links = "\n\n".join(content_with_links_parts)

    # Finalize status
    link_placement_status["success"] = (link_placement_status["failed_groups"] == 0)

    # Log final status
    if link_placement_status["success"]:
        logger.info(f"✅ Link placement completed successfully: {len(section_groups)} groups processed")
    else:
        logger.warning(f"⚠️ Link placement partially failed: {link_placement_status['failed_groups']}/{link_placement_status['total_groups']} groups failed")
        logger.warning(f"Failed sections: {', '.join(link_placement_status['failed_sections'])}")

    logger.info(f"Combined content length: {len(combined_content_with_links)} chars")

    return combined_content_with_links, link_placement_status


def translate_content(content: str, target_language: str, topic: str, base_path: str = None,
                      token_tracker: TokenTracker = None, model_name: str = None,
                      content_type: str = "basic_articles", variables_manager=None) -> tuple:
    """
    Translates article content from Russian to target language.

    Args:
        content: Combined article content to translate
        target_language: Target language for translation
        topic: Article topic
        base_path: Path to save translation interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
        content_type: Content type for prompt selection
        variables_manager: Optional VariablesManager instance

    Returns:
        Tuple: (translated_content, translation_status)
    """
    logger.info(f"Starting translation to {target_language}...")

    # Initialize translation status tracking
    translation_status = {
        "success": False,
        "target_language": target_language,
        "original_length": len(content),
        "translated_length": 0,
        "error": None
    }

    # Skip translation if no content
    if not content or len(content.strip()) < 100:
        logger.warning("Content too short or empty, skipping translation")
        translation_status["success"] = False
        translation_status["error"] = "Content too short"
        return content, translation_status

    try:
        # Prepare messages for translation
        messages = _load_and_prepare_messages(
            content_type,
            "11_translation",
            {
                "content_to_translate": content,
                "language": target_language  # Pass target language for {language} placeholder
            },
            variables_manager=variables_manager,
            stage_name="translation"
        )

        # Make translation request (validation happens inside make_llm_request)
        original_length = len(content)

        # Import custom validator for translation
        from src.llm_validation import translation_validator

        response_obj, actual_model = make_llm_request(
            stage_name="translation",
            model_name=model_name or LLM_MODELS.get("translation"),
            messages=messages,
            token_tracker=token_tracker,
            base_path=base_path,
            temperature=0.3,
            validation_level="v3",
            custom_validator=translation_validator,
            original_length=original_length,
            target_language=target_language
        )

        translated_content = response_obj.choices[0].message.content
        translated_content = clean_llm_tokens(translated_content)

        # Hard validation: check length with retry
        translated_length = len(translated_content)
        min_expected_length = original_length * 0.80  # 80% threshold
        max_expected_length = original_length * 1.25  # 125% threshold

        if translated_length < min_expected_length:
            logger.warning(f"⚠️ Translation too short: {translated_length} chars < 80% of {original_length} ({translated_length/original_length*100:.1f}%)")
            raise Exception(f"Translation too short: {translated_length} chars < 80% of {original_length}")
        elif translated_length > max_expected_length:
            logger.warning(f"⚠️ Translation too long: {translated_length} chars > 125% of {original_length} ({translated_length/original_length*100:.1f}%)")
            raise Exception(f"Translation too long: {translated_length} chars > 125% of {original_length}")
        else:
            logger.info(f"✅ Translation length validated: {translated_length} chars ({translated_length/original_length*100:.1f}% of original)")

        # Update status
        translation_status["success"] = True
        translation_status["translated_length"] = len(translated_content)

        logger.info(f"✅ Translation completed: {translation_status['original_length']} → {translation_status['translated_length']} chars")

        # Save interaction
        if base_path:
            save_llm_interaction(
                base_path=base_path,
                stage_name="translation",
                messages=messages,
                response=translated_content,
                request_id="translation",
                extra_params={
                    "model": actual_model,
                    "target_language": target_language,
                    "original_length": translation_status["original_length"],
                    "translated_length": translation_status["translated_length"]
                }
            )

        return translated_content, translation_status

    except Exception as e:
        logger.error(f"❌ Translation failed: {e}", exc_info=True)
        translation_status["success"] = False
        translation_status["error"] = str(e)

        # Return original content on failure
        return content, translation_status


def translate_sections(sections: List[Dict], target_language: str, topic: str, base_path: str = None,
                      token_tracker: TokenTracker = None, model_name: str = None,
                      content_type: str = "basic_articles", variables_manager=None) -> tuple:
    """
    Translates generated sections one by one from Russian to target language.

    Args:
        sections: List of generated sections with content (from generate_article_by_sections)
        target_language: Target language for translation
        topic: Article topic
        base_path: Path to save translation interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
        content_type: Content type for prompt selection
        variables_manager: Optional VariablesManager instance

    Returns:
        Tuple: (translated_sections, translation_status)
    """
    logger.info(f"Starting section-by-section translation to {target_language}...")

    # Initialize translation status tracking
    translation_status = {
        "success": False,
        "target_language": target_language,
        "total_sections": len(sections),
        "translated_sections": 0,
        "failed_sections": [],
        "error_details": []
    }

    # Filter successful sections
    successful_sections = [s for s in sections if s.get("status") == "success" and s.get("content")]

    if not successful_sections:
        logger.warning("No successful sections to translate")
        translation_status["success"] = True  # Nothing to translate = success
        return sections, translation_status

    logger.info(f"Translating {len(successful_sections)} sections to {target_language}")

    translated_sections = []

    # Translate each section separately
    for section in successful_sections:
        section_num = section.get("section_num")
        section_title = section.get("section_title", f"Section {section_num}")
        section_content = section.get("content", "")

        # Create section-specific path
        section_path = os.path.join(base_path, f"section_{section_num}") if base_path else None
        if section_path:
            os.makedirs(section_path, exist_ok=True)

        # Retry and fallback handled inside _make_llm_request_with_retry
        try:
            # Prepare messages for section translation
            messages = _load_and_prepare_messages(
                content_type,
                "09_translation",  # Translation is stage 9
                {
                    "content_to_translate": section_content,
                    "language": target_language,
                    "section_title": section_title
                },
                variables_manager=variables_manager,
                stage_name="translation"
            )

            # Make translation request with custom length validation
            from src.llm_request import make_llm_request
            from src.llm_validation import translation_validator

            original_length = len(section_content)

            response_obj, actual_model = make_llm_request(
                stage_name="translation",
                messages=messages,
                temperature=0.3,
                token_tracker=token_tracker,
                base_path=section_path,
                validation_level="v3",
                custom_validator=translation_validator,  # Custom validator with length check
                target_language=target_language,  # For language check in v3.0
                original_length=original_length  # For translation length ratio check (80-125%)
            )

            translated_content = response_obj.choices[0].message.content
            translated_content = clean_llm_tokens(translated_content)  # Clean LLM tokens

            # Validation is now done inside make_llm_request via translation_validator
            translated_length = len(translated_content)

            # Compact success log
            logger.info(f"Section {section_num}/{len(successful_sections)}: {section_title}... ✅ ({translated_length} chars, {translated_length/original_length*100:.0f}%)")

            # Save interaction
            if section_path:
                save_llm_interaction(
                    base_path=section_path,
                    stage_name="translation",
                    messages=messages,
                    response=translated_content,
                    request_id=f"section_{section_num}_translation",
                    extra_params={
                        "model": actual_model,
                        "section_num": section_num,
                        "section_title": section_title,
                        "target_language": target_language,
                        "original_length": len(section_content),
                        "translated_length": len(translated_content)
                    }
                )

            # Create translated section object
            translated_section = {
                "section_num": section_num,
                "section_title": section_title,
                "content": translated_content,
                "status": "translated",
                "original_content": section_content,  # Keep original for reference
                "translation_model": actual_model,
                "target_language": target_language
            }

            translated_sections.append(translated_section)
            translation_status["translated_sections"] += 1

            logger.info(f"✅ Section {section_num} | SUCCESS | Translated: {len(section_content)} → {len(translated_content)} chars")

            # Short delay between sections to avoid rate limits
            if section_num < len(successful_sections):
                time.sleep(2)

        except Exception as e:
            # All models failed (primary + fallback exhausted)
            logger.error(f"💥 Section {section_num} | FAILED after all retry attempts: {e}")
            translation_status["failed_sections"].append(section_num)
            translation_status["error_details"].append({
                "section_num": section_num,
                "section_title": section_title,
                "error": str(e)
            })

            # Add original section with error status
            translated_sections.append({
                "section_num": section_num,
                "section_title": section_title,
                "content": section_content,  # Keep original
                "status": "translation_failed",
                "error": str(e)
            })

    # Update final status
    translation_status["success"] = len(translation_status["failed_sections"]) == 0

    return translated_sections, translation_status


def create_structure(extracted_structures: List[List[Dict]], topic: str, 
                    base_path: str = None, token_tracker=None,
                    model_name: str = None, content_type: str = "basic_articles",
                    variables_manager=None) -> List[Dict]:
    """
    Wrapper for creating ultimate structure from extracted structures.
    Used primarily for testing the retry/fallback mechanism.
    
    Args:
        extracted_structures: List of structure lists from different sources
        topic: Topic of the article
        base_path: Base path for saving artifacts (optional)
        token_tracker: Token tracker instance (optional)
        model_name: LLM model to use (optional)
        content_type: Content type (default: basic_articles)
        variables_manager: Variables manager instance (optional)
        
    Returns:
        List of section dictionaries (article_structure)
    """
    try:
        messages = _load_and_prepare_messages(
            content_type,
            "02_create_ultimate_structure",
            {"topic": topic, "article_text": json.dumps(extracted_structures, indent=2)},
            variables_manager=variables_manager,
            stage_name="create_structure"
        )
        
        # Use unified LLM request with automatic fallback
        response_obj, actual_model = make_llm_request(
            stage_name="create_structure",
            messages=messages,
            temperature=0.3,
            token_tracker=token_tracker,
            base_path=base_path,
            validation_level="minimal"
        )
        
        content = response_obj.choices[0].message.content
        
        if base_path:
            save_llm_interaction(
                base_path=base_path,
                stage_name="create_structure",
                messages=messages,
                response=content,
                request_id="ultimate_structure"
            )
        
        ultimate_structure = _parse_json_from_response(content)
        
        # Normalize structure: handle both dict and list formats
        if isinstance(ultimate_structure, list):
            # LLM returned array - wrap it
            ultimate_structure = {
                "article_structure": ultimate_structure,
                "writing_guidelines": {}
            }
        elif isinstance(ultimate_structure, dict):
            # Check if it has expected keys
            if "article_structure" not in ultimate_structure:
                ultimate_structure = {
                    "article_structure": ultimate_structure.get("sections", [ultimate_structure]),
                    "writing_guidelines": ultimate_structure.get("writing_guidelines", {})
                }
        
        # Return just the sections list
        return ultimate_structure.get("article_structure", [])
        
    except Exception as e:
        logger.error(f"create_structure failed: {e}")
        # Graceful fallback: return first extracted structure
        if extracted_structures and len(extracted_structures) > 0:
            return extracted_structures[0] if isinstance(extracted_structures[0], list) else [extracted_structures[0]]
        return []
