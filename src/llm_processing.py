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
        stage_name: Название этапа (например, "extract_prompts")
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
    - extract_prompts: массив структур [{"section_title": ..., ...}, ...]
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

        # ADD VARIABLE ADDONS if variables_manager is provided
        if variables_manager and stage_name:
            # Map function name to config stage name
            config_stage = variables_manager.get_stage_mapping(stage_name)
            addon = variables_manager.get_stage_addon(config_stage)

            if addon:
                # Add addon at the beginning of user content for better LLM influence
                user_content = f"{addon}\n\n{user_content}"
                logger.debug(f"Added variable addon to {stage_name} prompt ({len(addon)} chars)")

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
    Makes LLM request with timeout and immediate fallback on timeout.

    Returns:
        tuple: (response_obj, actual_model_used)
    """
    primary_model = model_name or LLM_MODELS.get(stage_name, DEFAULT_MODEL)
    fallback_model = FALLBACK_MODELS.get(stage_name)

    models_to_try = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models_to_try.append(fallback_model)
        logger.info(f"📌 Fallback model available for {stage_name}: {fallback_model}")
    else:
        logger.info(f"⚠️ No fallback model configured for {stage_name}, will only try primary model")

    for model_index, current_model in enumerate(models_to_try):
        model_label = "primary" if model_index == 0 else "fallback"
        logger.info(f"🤖 Using {model_label} model for {stage_name}: {current_model} (timeout: {timeout}s)")

        try:
            # Make request with timeout
            def make_request():
                return _make_llm_request_with_retry_sync(stage_name, current_model, messages, token_tracker, base_path, **kwargs)

            loop = asyncio.get_event_loop()
            response_obj, actual_model = await asyncio.wait_for(
                loop.run_in_executor(None, make_request),
                timeout=timeout
            )

            logger.info(f"✅ Model {current_model} responded successfully ({model_label})")
            return response_obj, actual_model

        except asyncio.TimeoutError:
            logger.warning(f"⏰ TIMEOUT: Model {current_model} timed out after {timeout}s ({model_label} for {stage_name})")
            if model_index == len(models_to_try) - 1:  # Last model
                logger.error(f"🚨 ALL MODELS TIMED OUT for {stage_name}. Models tried: {models_to_try}")
                raise Exception(f"All models timed out for {stage_name}: {models_to_try}")
            else:
                next_model = models_to_try[model_index + 1] if model_index + 1 < len(models_to_try) else "unknown"
                logger.info(f"🔄 FALLBACK: Trying fallback model {next_model} after timeout...")
                continue

        except Exception as e:
            logger.warning(f"❌ Model {current_model} failed ({model_label}): {e}")
            if model_index == len(models_to_try) - 1:  # Last model
                logger.error(f"🚨 All models failed for stage {stage_name}. Models tried: {models_to_try}")
                raise Exception(f"All models failed for {stage_name}: {models_to_try}")
            else:
                logger.info(f"🔄 Trying fallback model...")

    raise Exception(f"All models failed for {stage_name}: {models_to_try}")


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

    if "candidates" not in result or not result["candidates"]:
        raise Exception("No candidates in Google API response")

    candidate = result["candidates"][0]

    if "content" not in candidate:
        raise Exception("No content in Google API response")

    # CRITICAL FIX: Gemini can return multiple parts, we need to combine them!
    parts = candidate["content"]["parts"]
    logger.info(f"🔍 Gemini returned {len(parts)} part(s) in response")

    # Combine all text parts
    content_parts = []
    for idx, part in enumerate(parts):
        if "text" in part:
            part_text = part["text"]
            content_parts.append(part_text)
            logger.info(f"   Part {idx+1}: {len(part_text)} chars")

    content = "".join(content_parts)
    logger.info(f"📏 Total combined content: {len(content)} chars")

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


def _make_llm_request_with_retry_sync(stage_name: str, model_name: str, messages: list,
                                token_tracker: TokenTracker = None, base_path: str = None, **kwargs) -> tuple:
    """
    Synchronous version of LLM request with retry logic (no timeout handling).
    Used by async timeout wrapper.

    Returns:
        tuple: (response_obj, actual_model_used)
    """
    for attempt in range(RETRY_CONFIG["max_attempts"]):
        try:
            client = get_llm_client(model_name)

            # Handle Google's direct API
            if client == "google_direct":
                response_obj = _make_google_direct_request(model_name, messages, **kwargs)
            else:
                response_obj = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    **kwargs
                )

            # СОХРАНЕНИЕ СЫРОГО ОТВЕТА В ПАПКЕ ЭТАПА
            raw_response_content = response_obj.choices[0].message.content

            # DEBUG: Log response content size in retry function
            logger.info(f"🔍 RETRY FUNCTION RAW_RESPONSE: {len(raw_response_content)} chars")

            # Сохраняем сырой ответ в папку этапа если base_path передан
            if base_path:
                try:
                    responses_dir = os.path.join(base_path, "llm_responses_raw")
                    os.makedirs(responses_dir, exist_ok=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    response_file = os.path.join(responses_dir, f"{stage_name}_response_attempt{attempt+1}_{timestamp}.txt")

                    with open(response_file, 'w', encoding='utf-8') as f:
                        f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
                        f.write(f"MODEL: {model_name}\n")
                        f.write(f"STAGE: {stage_name}\n")
                        f.write(f"ATTEMPT: {attempt + 1}\n")
                        f.write(f"RESPONSE_LENGTH: {len(raw_response_content)}\n")
                        f.write(f"SUCCESS: True\n")
                        f.write("=" * 80 + "\n")
                        f.write(raw_response_content)
                    logger.info(f"💾 RAW RESPONSE SAVED: {response_file}")
                except Exception as save_error:
                    logger.error(f"❌ Failed to save raw response: {save_error}")

            # Диагностика ответа API
            finish_reason = response_obj.choices[0].finish_reason
            content_length = len(raw_response_content)
            logger.info(f"🔍 API Response Debug:")
            logger.info(f"   finish_reason: {finish_reason}")
            logger.info(f"   content_length: {content_length}")
            logger.info(f"   usage: {response_obj.usage}")
            if hasattr(response_obj.choices[0], 'logprobs'):
                logger.info(f"   logprobs: {response_obj.choices[0].logprobs}")

            # Log successful model usage
            logger.info(f"✅ Model {model_name} responded successfully (attempt {attempt + 1})")

            # Track token usage with actual model info
            if token_tracker and response_obj.usage:
                provider = get_provider_for_model(model_name)
                token_tracker.add_usage(
                    stage=stage_name,
                    usage=response_obj.usage,
                    extra_metadata={
                        "model": model_name,
                        "provider": provider,
                        "attempt": attempt + 1
                    }
                )

            return response_obj, model_name

        except Exception as e:
            logger.warning(f"❌ Model {model_name} failed (attempt {attempt + 1}): {e}")

            # СОХРАНЕНИЕ ОШИБОЧНОГО ОТВЕТА В ПАПКЕ ЭТАПА (если ответ получен, но с ошибкой парсинга)
            if base_path and "response_obj" in locals() and hasattr(response_obj, 'choices') and response_obj.choices:
                try:
                    error_response_content = response_obj.choices[0].message.content
                    responses_dir = os.path.join(base_path, "llm_responses_raw")
                    os.makedirs(responses_dir, exist_ok=True)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    error_file = os.path.join(responses_dir, f"ERROR_{stage_name}_response_attempt{attempt+1}_{timestamp}.txt")

                    with open(error_file, 'w', encoding='utf-8') as f:
                        f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
                        f.write(f"MODEL: {model_name}\n")
                        f.write(f"STAGE: {stage_name}\n")
                        f.write(f"ATTEMPT: {attempt + 1}\n")
                        f.write(f"ERROR: {str(e)}\n")
                        f.write(f"RESPONSE_LENGTH: {len(error_response_content)}\n")
                        f.write(f"SUCCESS: False\n")
                        f.write("=" * 80 + "\n")
                        f.write(error_response_content)
                    logger.error(f"💾 ERROR RESPONSE SAVED: {error_file}")
                except Exception as save_error:
                    logger.error(f"❌ Failed to save error response: {save_error}")

            # If not the last attempt, wait before retrying
            if attempt < RETRY_CONFIG["max_attempts"] - 1:
                delay = RETRY_CONFIG["delays"][attempt]
                logger.info(f"⏳ Waiting {delay}s before retry...")
                time.sleep(delay)
            else:
                logger.error(f"💥 Model {model_name} exhausted all {RETRY_CONFIG['max_attempts']} attempts")

    # Model failed after all retries
    raise Exception(f"Model {model_name} failed for {stage_name} after {RETRY_CONFIG['max_attempts']} attempts")


def _make_llm_request_with_retry(stage_name: str, model_name: str, messages: list,
                                token_tracker: TokenTracker = None, base_path: str = None, **kwargs) -> tuple:
    """
    Legacy wrapper for backward compatibility. Uses the old sync retry logic.
    """
    primary_model = model_name or LLM_MODELS.get(stage_name, DEFAULT_MODEL)
    fallback_model = FALLBACK_MODELS.get(stage_name)

    models_to_try = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models_to_try.append(fallback_model)
        logger.info(f"📌 Fallback model available for {stage_name}: {fallback_model}")
    else:
        logger.info(f"⚠️ No fallback model configured for {stage_name}, will only try primary model")

    for model_index, current_model in enumerate(models_to_try):
        model_label = "primary" if model_index == 0 else "fallback"
        logger.info(f"🤖 Using {model_label} model for {stage_name}: {current_model}")

        try:
            return _make_llm_request_with_retry_sync(stage_name, current_model, messages, token_tracker, base_path, **kwargs)
        except Exception as e:
            logger.warning(f"❌ Model {current_model} failed ({model_label}): {e}")
            if model_index == len(models_to_try) - 1:  # Last model
                logger.error(f"🚨 All models failed for stage {stage_name}. Models tried: {models_to_try}")
                raise Exception(f"All models failed for {stage_name}: {models_to_try}")
            else:
                logger.info(f"🔄 Trying fallback model...")
                continue


def extract_prompts_from_article(article_text: str, topic: str, base_path: str = None,
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
            stage_name="extract_prompts"
        )

        # Use new retry system
        response, actual_model = _make_llm_request_with_retry(
            stage_name="extract_prompts",
            model_name=model_name,
            messages=messages,
            token_tracker=token_tracker,
            base_path=base_path,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        content = clean_llm_tokens(content)  # Очищаем токены LLM

        # Сохраняем запрос и ответ для отладки
        if base_path:
            save_llm_interaction(
                base_path=base_path,
                stage_name="extract_prompts",
                messages=messages,
                response=content,
                request_id=source_id or "single",
                extra_params={"response_format": "json_object", "topic": topic, "model": actual_model}
            )
        
        parsed_json = _parse_json_from_response(content)
        if isinstance(parsed_json, list):
            return parsed_json
        elif isinstance(parsed_json, dict):
            return parsed_json.get("data", [parsed_json])  # If no data key, return object wrapped in array
        else:
            return []
    except Exception as e:
        logger.error(f"Failed to extract prompts via API: {e}")
        return []






async def _generate_single_section_async(section: Dict, idx: int, topic: str,
                                        sections_path: str, model_name: str,
                                        token_tracker: TokenTracker, content_type: str = "basic_articles") -> Dict:
    """Generates a single section asynchronously with proper timeout and fallback handling."""
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

    for attempt in range(1, SECTION_MAX_RETRIES + 1):
        try:
            logger.info(f"🔄 Section {idx} attempt {attempt}/{SECTION_MAX_RETRIES}: {section_title}")

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

            # Use new timeout-aware request function
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

            # Validate content
            if not section_content or len(section_content.strip()) < 50:
                logger.warning(f"⚠️ Section {idx} attempt {attempt} returned insufficient content")
                if attempt < SECTION_MAX_RETRIES:
                    await asyncio.sleep(3)  # Wait 3 seconds before retry
                    continue
                else:
                    raise Exception("All attempts returned insufficient content")

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
                        "model": actual_model,
                        "attempt": attempt
                    }
                )

            logger.info(f"✅ Successfully generated section {idx} (attempt {attempt}): {section_title}")

            result = {
                "section_num": idx,
                "section_title": section.get("section_title", ""),
                "content": section_content,
                "status": "success",
                "attempts": attempt
            }

            logger.info(f"🎯 Section {idx} COMPLETED and returning result")
            return result

        except Exception as e:
            logger.error(f"❌ Section {idx} attempt {attempt} failed: {e}")
            if attempt < SECTION_MAX_RETRIES:
                wait_time = attempt * 5  # Progressive backoff: 5s, 10s, 15s
                logger.info(f"⏳ Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"💥 Section {idx} failed after {SECTION_MAX_RETRIES} attempts")
                return {
                    "section_num": idx,
                    "section_title": section.get("section_title", ""),
                    "content": f"<p>Не удалось сгенерировать раздел '{section_title}' после {SECTION_MAX_RETRIES} попыток. Последняя ошибка: {str(e)}</p>",
                    "status": "failed",
                    "error": str(e),
                    "attempts": SECTION_MAX_RETRIES
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
            logger.info(f"📚 Preparing context from {len(generated_sections)} previous sections")
            ready_sections_parts = []
            for prev_section in generated_sections:
                if prev_section.get("status") == "success" and prev_section.get("content"):
                    prev_title = prev_section.get("section_title", f"Раздел {prev_section.get('section_num', '')}")
                    prev_content = prev_section.get("content", "")
                    ready_sections_parts.append(f"РАЗДЕЛ: {prev_title}\n{prev_content}")

            ready_sections = "\n\n".join(ready_sections_parts) if ready_sections_parts else "Предыдущие разделы недоступны."
            logger.info(f"📚 Context prepared: {len(ready_sections)} characters from {len(ready_sections_parts)} sections")

        logger.info(f"📝 Generating section {idx}/{total_sections}: {section_title}")

        for attempt in range(1, SECTION_MAX_RETRIES + 1):
            try:
                logger.info(f"🔄 Section {idx} attempt {attempt}/{SECTION_MAX_RETRIES}: {section_title}")

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

                # Make SYNCHRONOUS request
                response_obj, actual_model = _make_llm_request_with_retry_sync(
                    stage_name="generate_article",
                    model_name=model_name or LLM_MODELS.get("generate_article", DEFAULT_MODEL),
                    messages=messages,
                    token_tracker=token_tracker,
                    base_path=section_path,
                    temperature=0.3
                )

                section_content = response_obj.choices[0].message.content
                section_content = clean_llm_tokens(section_content)  # Очищаем токены LLM

                # Validate content
                if not section_content or len(section_content.strip()) < 50:
                    logger.warning(f"⚠️ Section {idx} attempt {attempt} returned insufficient content")
                    if attempt < SECTION_MAX_RETRIES:
                        time.sleep(3)  # Wait 3 seconds before retry
                        continue
                    else:
                        raise Exception("All attempts returned insufficient content")

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
                            "model": actual_model,
                            "attempt": attempt
                        }
                    )

                logger.info(f"✅ Successfully generated section {idx}/{total_sections}: {section_title}")

                result = {
                    "section_num": idx,
                    "section_title": section.get("section_title", ""),
                    "content": section_content,
                    "status": "success",
                    "attempts": attempt
                }

                generated_sections.append(result)
                logger.info(f"📚 Section {idx} added to context for next sections")
                break  # Success, exit retry loop

            except Exception as e:
                logger.error(f"❌ Section {idx} attempt {attempt} failed: {e}")
                if attempt < SECTION_MAX_RETRIES:
                    wait_time = attempt * 5  # Progressive backoff: 5s, 10s, 15s
                    logger.info(f"⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"💥 Section {idx} failed after {SECTION_MAX_RETRIES} attempts")
                    result = {
                        "section_num": idx,
                        "section_title": section.get("section_title", ""),
                        "content": f"<p>Не удалось сгенерировать раздел '{section_title}' после {SECTION_MAX_RETRIES} попыток. Последняя ошибка: {str(e)}</p>",
                        "status": "failed",
                        "error": str(e),
                        "attempts": SECTION_MAX_RETRIES
                    }
                    generated_sections.append(result)
                    break  # Give up on this section

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

    # Filter successful sections
    successful_sections = [s for s in sections if s.get("status") == "success" and s.get("content")]

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
                "09_fact_check",
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

            # Make fact-check request
            response_obj, actual_model = _make_llm_request_with_retry(
                stage_name="fact_check",
                model_name=model_name or LLM_MODELS.get("fact_check"),
                messages=messages,
                token_tracker=token_tracker,
                base_path=group_path,
                temperature=0.2  # Low temperature for factual accuracy
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
            logger.error(f"❌ Fact-check failed for group {group_num}: {e}")

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
            },
            variables_manager=variables_manager,
            stage_name="editorial_review"
        )
    except Exception as e:
        logger.error(f"Failed to load editorial review prompt: {e}")
        return _create_error_response(topic, f"Ошибка загрузки промпта: {str(e)}", "prompt-error")

    # Get models to try
    primary_model = model_name or LLM_MODELS.get("editorial_review", DEFAULT_MODEL)
    fallback_model = FALLBACK_MODELS.get("editorial_review")

    models_to_try = [
        {"model": primary_model, "label": "primary"},
        {"model": fallback_model, "label": "fallback"} if fallback_model and fallback_model != primary_model else None
    ]
    models_to_try = [m for m in models_to_try if m is not None]

    logger.info(f"🎯 Editorial review plan: {len(models_to_try)} model(s) to try")
    for i, model_info in enumerate(models_to_try):
        logger.info(f"   {i+1}. {model_info['label']}: {model_info['model']}")

    # Main retry loop with models
    for model_index, model_info in enumerate(models_to_try):
        current_model = model_info["model"]
        model_label = model_info["label"]

        logger.info(f"🤖 Attempting editorial review with {model_label} model: {current_model}")

        # Retry loop for current model (3 attempts)
        for attempt in range(1, 4):
            logger.info(f"📝 Editorial review attempt {attempt}/3 with {model_label} model...")

            try:
                # Make LLM request (this handles its own retries internally)
                response_obj, actual_model = _make_llm_request_with_retry_sync(
                    stage_name="editorial_review",
                    model_name=current_model,
                    messages=messages,
                    token_tracker=token_tracker,
                    base_path=base_path,
                    temperature=0.2,
                    response_format={"type": "json_object"} if not current_model.startswith("perplexity/") else None
                )

                response = response_obj.choices[0].message.content
                response = clean_llm_tokens(response)  # Очищаем токены LLM

                # Save interaction with attempt info
                if base_path:
                    save_llm_interaction(
                        base_path=base_path,
                        stage_name="editorial_review",
                        messages=messages,
                        response=response,
                        request_id=f"{model_label}_attempt_{attempt}",
                        extra_params={
                            "topic": topic,
                            "model_label": model_label,
                            "attempt": attempt,
                            "model": actual_model
                        }
                    )

                # Try to parse JSON with normalization (4 attempts)
                parsed_result = _try_parse_editorial_json(response, actual_model, attempt, model_label)

                if parsed_result is not None:
                    logger.info(f"✅ Editorial review SUCCESS on {model_label} model, attempt {attempt}")
                    logger.info(f"📄 Article title: {parsed_result.get('title', 'No title')}")
                    return parsed_result
                else:
                    logger.warning(f"❌ JSON parsing failed for {model_label} model, attempt {attempt}")

            except Exception as e:
                logger.error(f"❌ {model_label} model attempt {attempt} failed with exception: {e}")

        logger.warning(f"💥 All 3 attempts failed for {model_label} model: {current_model}")

    # All models and attempts failed
    logger.error(f"🚨 EDITORIAL REVIEW COMPLETELY FAILED - all models exhausted")
    logger.error(f"Models tried: {[m['model'] for m in models_to_try]}")

    return _create_error_response(
        topic,
        "Не удалось выполнить редакторскую правку после всех попыток с основной и резервной моделями",
        "editorial-failure"
    )


def _try_parse_editorial_json(response: str, model_name: str, attempt: int, model_label: str) -> Dict[str, Any]:
    """
    Attempts to parse JSON from editorial review response with 4 normalization attempts.

    Returns:
        Parsed JSON dict if successful, None if failed
    """
    logger.info(f"🔍 Parsing JSON from {model_label} model (attempt {attempt})...")

    # Attempt 1: Direct parsing
    try:
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
            # Standard cleanup
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]

        cleaned_response = cleaned_response.strip()
        parsed = json.loads(cleaned_response)
        logger.info("✅ Direct JSON parsing successful")
        return parsed

    except json.JSONDecodeError as e:
        logger.info(f"❌ Direct parsing failed: {e}")

    # Attempts 2-4: Enhanced normalization
    import re

    for cleanup_attempt in range(1, 4):
        logger.info(f"🛠️ JSON normalization attempt {cleanup_attempt}/3...")

        try:
            if cleanup_attempt == 1:
                # Fix common escaping issues
                fixed_response = response.strip()
                fixed_response = re.sub(r'\\\\"', '"', fixed_response)
                fixed_response = re.sub(r'class="([^"]*)"', r"class='\1'", fixed_response)
                fixed_response = re.sub(r'language-([^"]*)"', r"language-\1'", fixed_response)

            elif cleanup_attempt == 2:
                # Extract JSON block
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if not json_match:
                    continue
                fixed_response = json_match.group(0)

            elif cleanup_attempt == 3:
                # Fix incomplete JSON
                fixed_response = response.strip()
                brace_count = fixed_response.count('{') - fixed_response.count('}')
                if brace_count > 0:
                    fixed_response += '}' * brace_count

            # Try parsing
            parsed = json.loads(fixed_response)
            logger.info(f"✅ JSON normalization attempt {cleanup_attempt} successful")
            return parsed

        except json.JSONDecodeError:
            logger.info(f"❌ Normalization attempt {cleanup_attempt} failed")
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
