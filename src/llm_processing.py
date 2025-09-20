import os
import json
import re
import time
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv
import openai

from src.logger_config import logger
from src.token_tracker import TokenTracker
from src.config import LLM_MODELS, DEFAULT_MODEL, LLM_PROVIDERS, get_provider_for_model, FALLBACK_MODELS, RETRY_CONFIG, SECTION_TIMEOUT, MODEL_TIMEOUT, SECTION_MAX_RETRIES

# Загружаем переменные среды
load_dotenv()

# Словарь для кэширования клиентов
_clients_cache = {}

def clear_llm_clients_cache():
    """Очищает кэш LLM клиентов для освобождения памяти."""
    global _clients_cache
    _clients_cache.clear()
    logger.info("LLM clients cache cleared")

def get_llm_client(model_name: str) -> openai.OpenAI:
    """Get appropriate LLM client for the given model."""
    provider = get_provider_for_model(model_name)
    
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
        
        # Сохраняем ответ
        response_path = os.path.join(responses_dir, response_filename)
        with open(response_path, 'w', encoding='utf-8') as f:
            f.write(response)
        
        logger.info(f"Saved LLM interaction: {request_path} + {response_path}")
        
    except Exception as e:
        logger.error(f"Failed to save LLM interaction: {e}")

def _parse_json_from_response(response_content: str) -> Any:
    """
    Robustly parses JSON from LLM response, handling various formats:
    - Single objects: {...}
    - Arrays: [{...}, {...}]
    - Objects with data wrapper: {"data": [...]}
    - Malformed JSON with common errors
    - Escape character issues from LLM responses
    - Control characters in editorial review responses
    """
    response_content = response_content.strip()
    
    if not response_content:
        logger.error("Empty response content")
        return []
    
    # Attempt 1: Parse as-is
    try:
        parsed = json.loads(response_content)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            return parsed.get("data", [parsed])  # If has data key, use it; otherwise wrap single object
        else:
            return []
    except json.JSONDecodeError as e:
        logger.warning(f"Standard JSON parsing failed: {e}")
        pass
    
    # Attempt 1.5: Enhanced JSON preprocessing (for editorial review control characters)
    try:
        logger.info("Attempting enhanced JSON parsing...")
        fixed_content = response_content
        
        # Remove code block wrappers if present
        if fixed_content.startswith('```json\n') and fixed_content.endswith('\n```'):
            fixed_content = fixed_content[8:-4].strip()
        elif fixed_content.startswith('```\n') and fixed_content.endswith('\n```'):
            fixed_content = fixed_content[4:-4].strip()
        
        # Fix control characters that cause "Invalid control character" errors
        # Replace unescaped control characters within JSON string values
        fixed_content = re.sub(r'(:\s*")([^"]*?)(")', lambda m: m.group(1) + m.group(2).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + m.group(3), fixed_content)
        
        # Fix escaped underscores in JSON keys (aggressive approach)
        fixed_content = fixed_content.replace('prompt\\_text', 'prompt_text')
        fixed_content = fixed_content.replace('expert\\_description', 'expert_description')
        fixed_content = fixed_content.replace('why\\_good', 'why_good')
        fixed_content = fixed_content.replace('how\\_to\\_improve', 'how_to_improve')
        
        # Fix any remaining backslash-underscore patterns
        fixed_content = re.sub(r'\\\\_', '_', fixed_content)
        
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
            return parsed
        else:
            return []
    except json.JSONDecodeError as e:
        logger.warning(f"Enhanced JSON parsing failed: {e}")
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
            return parsed.get("data", [parsed])
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse extracted JSON string: {e}")
        logger.error(f"String: {response_content[:1000]}")
        return []


def _load_and_prepare_messages(article_type: str, prompt_name: str, replacements: Dict[str, str]) -> List[Dict]:
    """Loads a prompt template, performs replacements, and splits into messages."""
    path = os.path.join("prompts", article_type, f"{prompt_name}.txt")
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

        messages = []
        if system_content:
            messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": user_content})
        
        return messages

    except FileNotFoundError:
        logger.error(f"Prompt file not found: {path}")
        raise


async def _make_llm_request_with_timeout(stage_name: str, model_name: str, messages: list,
                                        token_tracker: TokenTracker = None, timeout: int = MODEL_TIMEOUT, **kwargs) -> tuple:
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
                return _make_llm_request_with_retry_sync(stage_name, current_model, messages, token_tracker, **kwargs)

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


def _make_llm_request_with_retry_sync(stage_name: str, model_name: str, messages: list,
                                token_tracker: TokenTracker = None, **kwargs) -> tuple:
    """
    Synchronous version of LLM request with retry logic (no timeout handling).
    Used by async timeout wrapper.

    Returns:
        tuple: (response_obj, actual_model_used)
    """
    for attempt in range(RETRY_CONFIG["max_attempts"]):
        try:
            client = get_llm_client(model_name)

            response_obj = client.chat.completions.create(
                model=model_name,
                messages=messages,
                **kwargs
            )

            # Диагностика ответа API
            finish_reason = response_obj.choices[0].finish_reason
            content_length = len(response_obj.choices[0].message.content)
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
                                token_tracker: TokenTracker = None, **kwargs) -> tuple:
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
            return _make_llm_request_with_retry_sync(stage_name, current_model, messages, token_tracker, **kwargs)
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
                                 model_name: str = None) -> List[Dict]:
    """Extracts structured prompt data from a single article text.

    Args:
        article_text: The text content to extract prompts from
        topic: The topic for context
        base_path: Path to save LLM interactions
        source_id: Identifier for the source
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
    """
    logger.info("Extracting prompts from one article...")
    try:
        messages = _load_and_prepare_messages(
            "basic_articles",
            "01_extract",
            {"topic": topic, "article_text": article_text}
        )

        # Use new retry system
        response, actual_model = _make_llm_request_with_retry(
            stage_name="extract_prompts",
            model_name=model_name,
            messages=messages,
            token_tracker=token_tracker,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        
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


async def extract_prompts_from_article_async(article_text: str, topic: str, base_path: str = None,
                                           source_id: str = None, token_tracker: TokenTracker = None,
                                           model_name: str = None, source_index: int = 1) -> List[Dict]:
    """Async version of extract_prompts_from_article with HTTP request delays.

    Args:
        article_text: The text content to extract prompts from
        topic: The topic for context
        base_path: Path to save LLM interactions
        source_id: Identifier for the source
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
        source_index: Index of source for staggered delays (1-based)
    """
    # Wait for HTTP request timing - each source waits (source_index-1)*5 seconds
    if source_index > 1:
        http_delay = (source_index - 1) * 5
        logger.info(f"⏳ {source_id} waiting {http_delay}s before HTTP request...")
        await asyncio.sleep(http_delay)

    logger.info(f"Extracting prompts from {source_id}...")
    try:
        messages = _load_and_prepare_messages(
            "basic_articles",
            "01_extract",
            {"topic": topic, "article_text": article_text}
        )

        # Execute LLM request with timeout using thread pool
        def make_request():
            return _make_llm_request_with_retry(
                stage_name="extract_prompts",
                model_name=model_name,
                messages=messages,
                token_tracker=token_tracker,
                temperature=0.3,
            )

        # Run in executor to make it async
        loop = asyncio.get_event_loop()
        response, actual_model = await loop.run_in_executor(None, make_request)
        content = response.choices[0].message.content

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
        logger.error(f"Failed to extract prompts from {source_id} via API: {e}")
        return []


def generate_wordpress_article(prompts: List[Dict], topic: str, base_path: str = None,
                              token_tracker: TokenTracker = None, model_name: str = None) -> Dict[str, Any]:
    """Generates a WordPress-ready article from collected prompts.

    Args:
        prompts: List of collected prompts to use for article generation
        topic: The topic for the article
        base_path: Path to save LLM interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
    """
    logger.info("Generating WordPress article from collected prompts...")
    try:
        messages = _load_and_prepare_messages(
            "basic_articles",
            "01_generate_wordpress_article",
            {"topic": topic, "article_text": json.dumps(prompts, indent=2, ensure_ascii=False)}
        )

        # Use new retry system
        response_obj, actual_model = _make_llm_request_with_retry(
            stage_name="generate_article",
            model_name=model_name,
            messages=messages,
            token_tracker=token_tracker,
            temperature=0.3,
            response_format={"type": "json_object"}  # Enforce JSON response
        )
        response = response_obj.choices[0].message.content

        # Сохраняем запрос и ответ для отладки
        if base_path:
            save_llm_interaction(
                base_path=base_path,
                stage_name="generate_wordpress_article",
                messages=messages,
                response=response,
                extra_params={
                    "topic": topic,
                    "input_prompts_count": len(prompts),
                    "purpose": "generate_wordpress_article",
                    "response_format": "json_object",
                    "model": actual_model
                }
            )
        
        # Просто возвращаем сырой ответ от LLM - пусть editorial_review обрабатывает
        logger.info(f"Generated article from LLM, response length: {len(response)} characters")
        return {"raw_response": response, "topic": topic}
            
    except Exception as e:
        logger.error(f"Failed to generate WordPress article: {e}")
        return {"raw_response": f"ERROR: {str(e)}", "topic": topic}


async def _generate_single_section_async(section: Dict, idx: int, topic: str,
                                        sections_path: str, model_name: str,
                                        token_tracker: TokenTracker) -> Dict:
    """Generates a single section asynchronously with proper timeout and fallback handling."""
    section_num = f"section_{idx}"
    section_title = section.get('section_title', f'Section {idx}')

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
                "basic_articles",
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
                temperature=0.3
            )

            section_content = response_obj.choices[0].message.content

            # Validate content
            if not section_content or len(section_content.strip()) < 50:
                logger.warning(f"⚠️ Section {idx} attempt {attempt} returned insufficient content")
                if attempt < SECTION_MAX_RETRIES:
                    await asyncio.sleep(3)  # Wait 3 seconds before retry
                    continue
                else:
                    raise Exception("All attempts returned insufficient content")

            # Save section interaction
            if sections_path:
                section_path = os.path.join(sections_path, section_num)
                os.makedirs(section_path, exist_ok=True)

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
                                 token_tracker: TokenTracker = None, model_name: str = None) -> Dict[str, Any]:
    """Generates WordPress article by processing sections SEQUENTIALLY without any async operations.

    Args:
        structure: Ultimate structure with sections to generate
        topic: The topic for the article
        base_path: Path to save LLM interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)

    Returns:
        Dict with raw_response containing merged sections and metadata
    """
    logger.info(f"Starting SEQUENTIAL section-by-section article generation for topic: {topic}")

    # Parse actual ultimate_structure format
    actual_sections = []

    if isinstance(structure, list) and len(structure) > 0:
        if isinstance(structure[0], dict) and "article_structure" in structure[0]:
            actual_sections = structure[0]["article_structure"]
            logger.info(f"Found {len(actual_sections)} sections in article_structure")
        else:
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

    # Generate sections SEQUENTIALLY
    generated_sections = []

    for idx, section in enumerate(actual_sections, 1):
        section_num = f"section_{idx}"
        section_title = section.get('section_title', f'Section {idx}')

        logger.info(f"📝 Generating section {idx}/{total_sections}: {section_title}")

        for attempt in range(1, SECTION_MAX_RETRIES + 1):
            try:
                logger.info(f"🔄 Section {idx} attempt {attempt}/{SECTION_MAX_RETRIES}: {section_title}")

                # Prepare section-specific prompt
                messages = _load_and_prepare_messages(
                    "basic_articles",
                    "01_generate_section",
                    {
                        "topic": topic,
                        "section_title": section.get("section_title", ""),
                        "section_structure": json.dumps(section, indent=2, ensure_ascii=False)
                    }
                )

                # Make SYNCHRONOUS request
                response_obj, actual_model = _make_llm_request_with_retry_sync(
                    stage_name="generate_article",
                    model_name=model_name or LLM_MODELS.get("generate_article", DEFAULT_MODEL),
                    messages=messages,
                    token_tracker=token_tracker,
                    temperature=0.3
                )

                section_content = response_obj.choices[0].message.content

                # Validate content
                if not section_content or len(section_content.strip()) < 50:
                    logger.warning(f"⚠️ Section {idx} attempt {attempt} returned insufficient content")
                    if attempt < SECTION_MAX_RETRIES:
                        time.sleep(3)  # Wait 3 seconds before retry
                        continue
                    else:
                        raise Exception("All attempts returned insufficient content")

                # Save section interaction
                if sections_path:
                    section_path = os.path.join(sections_path, section_num)
                    os.makedirs(section_path, exist_ok=True)

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

    return {"raw_response": json.dumps(merged_content, ensure_ascii=False), "topic": topic}


def generate_article_by_sections_OLD_ASYNC(structure: List[Dict], topic: str, base_path: str = None,
                                 token_tracker: TokenTracker = None, model_name: str = None) -> Dict[str, Any]:
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

    # ИСПРАВЛЕНИЕ: парсим реальный формат ultimate_structure
    actual_sections = []

    if isinstance(structure, list) and len(structure) > 0:
        if isinstance(structure[0], dict) and "article_structure" in structure[0]:
            # Формат: [{"article_structure": [секции...]}]
            actual_sections = structure[0]["article_structure"]
            logger.info(f"Extracted {len(actual_sections)} sections from article_structure")
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

    return {"raw_response": json.dumps(merged_content, ensure_ascii=False), "topic": topic}


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
                       stripped.startswith('<li') or stripped.startswith('<br')):
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

    # Filter successful sections
    successful_sections = [s for s in sections if s.get("status") == "success" and s.get("content")]

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
                    token_tracker: TokenTracker = None, model_name: str = None) -> Dict[str, Any]:
    """
    Performs editorial review and cleanup of WordPress article data.

    Args:
        raw_response: Raw response string from generate_wordpress_article()
        topic: The topic for the article (used in editorial prompt)
        base_path: Path to save LLM interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)
    """
    logger.info("Starting editorial review and cleanup...")
    
    # Check for error responses
    if raw_response.startswith("ERROR:"):
        logger.error(f"Received error from previous stage: {raw_response}")
        return {
            "title": f"Ошибка генерации: {topic}",
            "content": f"<p>Ошибка на предыдущем этапе: {raw_response}</p>",
            "excerpt": "Ошибка генерации статьи",
            "slug": "generation-error",
            "categories": ["prompts"],
            "_yoast_wpseo_title": "Ошибка генерации",
            "_yoast_wpseo_metadesc": "Ошибка при генерации статьи",
            "image_caption": "Ошибка",
            "focus_keyword": "ошибка"
        }
    
    # Call LLM for editorial review
    try:
        messages = _load_and_prepare_messages(
            "basic_articles",
            "02_editorial_review",
            {
                "raw_response": raw_response,
                "topic": topic
            }
        )

        # Use new retry system
        response_obj, actual_model = _make_llm_request_with_retry(
            stage_name="editorial_review",
            model_name=model_name,
            messages=messages,
            token_tracker=token_tracker,
            temperature=0.2,  # Lower temperature for more consistent editing
            response_format={"type": "json_object"}  # Enforce JSON response
        )
        response = response_obj.choices[0].message.content

        # Save LLM interaction for debugging
        if base_path:
            save_llm_interaction(
                base_path=base_path,
                stage_name="editorial_review",
                messages=messages,
                response=response,
                extra_params={
                    "topic": topic,
                    "purpose": "editorial_review_and_cleanup",
                    "model": actual_model
                }
            )
        
        # Parse JSON response with enhanced error handling
        try:
            # Clean up response - extra cleaning for Gemini models
            cleaned_response = response.strip()

            # Special handling for Gemini models which often add markdown
            if "gemini" in actual_model.lower():
                logger.info("🧹 Applying Gemini-specific JSON cleanup...")
                # Remove markdown code blocks
                if cleaned_response.startswith('```'):
                    # Find the end of the first line (language specifier)
                    first_newline = cleaned_response.find('\n')
                    if first_newline > 0:
                        cleaned_response = cleaned_response[first_newline+1:]
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]
            else:
                # Standard cleanup for other models
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]

            cleaned_response = cleaned_response.strip()
            
            # Try to parse JSON
            edited_data = json.loads(cleaned_response)
            logger.info(f"Successfully completed editorial review: {edited_data.get('title', 'No title')}")
            return edited_data
            
        except json.JSONDecodeError as e:
            logger.warning(f"Standard JSON parsing failed: {e}")
            logger.info("Attempting enhanced JSON cleanup and parsing...")
            
            # Enhanced JSON cleaning attempts
            try:
                import re
                
                # Try multiple cleanup approaches
                for attempt in range(1, 5):
                    logger.info(f"JSON cleanup attempt {attempt}...")
                    
                    if attempt == 1:
                        # Basic cleanup - fix common escaping issues
                        fixed_response = response.strip()
                        # Fix double escaping
                        fixed_response = re.sub(r'\\\\"', '"', fixed_response)
                        # Fix unescaped quotes in HTML attributes
                        fixed_response = re.sub(r'class="([^"]*)"', r"class='\1'", fixed_response)
                        fixed_response = re.sub(r'language-([^"]*)"', r"language-\1'", fixed_response)
                        
                    elif attempt == 2:
                        # Try to extract JSON block from response
                        json_match = re.search(r'\{.*\}', response, re.DOTALL)
                        if json_match:
                            fixed_response = json_match.group(0)
                        else:
                            continue
                            
                    elif attempt == 3:
                        # Fix incomplete JSON (missing closing braces)
                        fixed_response = response.strip()
                        brace_count = fixed_response.count('{') - fixed_response.count('}')
                        if brace_count > 0:
                            fixed_response += '}' * brace_count
                            
                    elif attempt == 4:
                        # Last resort: extract JSON fields manually
                        extracted_data = {}
                        
                        # Extract title
                        title_match = re.search(r'"title":\s*"([^"]*(?:\\.[^"]*)*)"', response)
                        if title_match:
                            extracted_data["title"] = title_match.group(1).replace('\\"', '"')
                            
                        # Extract other fields
                        for field in ["excerpt", "slug", "_yoast_wpseo_title", "_yoast_wpseo_metadesc", "image_caption", "focus_keyword"]:
                            field_match = re.search(f'"{field}":\\s*"([^"]*(?:\\\\.[^"]*)*)"', response)
                            if field_match:
                                extracted_data[field] = field_match.group(1).replace('\\"', '"')
                        
                        # Extract categories
                        categories_match = re.search(r'"categories":\s*\[(.*?)\]', response, re.DOTALL)
                        if categories_match:
                            categories_str = categories_match.group(1)
                            categories = [cat.strip().strip('"') for cat in categories_str.split(',') if cat.strip()]
                            extracted_data["categories"] = categories
                        
                        # Extract content (complex)
                        content_match = re.search(r'"content":\s*"(.*?)(?=",\s*"[^"]+"|$)', response, re.DOTALL)
                        if content_match:
                            content = content_match.group(1)
                            # Basic unescape
                            content = content.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
                            extracted_data["content"] = content
                        
                        if len(extracted_data) >= 6:
                            logger.info(f"Manual field extraction successful: {len(extracted_data)} fields")
                            return extracted_data
                        else:
                            continue
                    
                    # Try to parse the fixed response
                    try:
                        edited_data = json.loads(fixed_response)
                        logger.info(f"JSON cleanup attempt {attempt} successful!")
                        return edited_data
                    except json.JSONDecodeError:
                        continue
                        
                # All attempts failed
                logger.error("All JSON cleanup attempts failed")
                
            except Exception as cleanup_err:
                logger.error(f"JSON cleanup failed: {cleanup_err}")
            
            # Final fallback - return error response
            logger.error(f"Response length: {len(response)} characters")
            logger.error(f"First 300 chars: {response[:300]}")
            logger.error(f"Last 300 chars: {response[-300:]}")
            
            return {
                "title": f"Ошибка парсинга JSON: {topic}",
                "content": f"<p>Не удалось распарсить JSON ответ от редактора после всех попыток очистки. Ответ получен полностью ({len(response)} символов).</p><details><summary>Сырой ответ</summary><pre>{response[:2000]}</pre></details>",
                "excerpt": "Ошибка парсинга JSON ответа",
                "slug": "json-parsing-error", 
                "categories": ["prompts"],
                "_yoast_wpseo_title": "Ошибка парсинга JSON",
                "_yoast_wpseo_metadesc": "Произошла ошибка при парсинге JSON ответа от редактора",
                "image_caption": "Ошибка парсинга JSON",
                "focus_keyword": "промпты"
            }
                
    except Exception as e:
        logger.error(f"Critical error during editorial review: {e}")
        return {
            "title": f"Критическая ошибка: {topic}",
            "content": f"<p>Критическая ошибка при редактуре: {str(e)}</p>",
            "excerpt": "Критическая ошибка обработки",
            "slug": "critical-error",
            "categories": ["prompts"],
            "_yoast_wpseo_title": "Критическая ошибка",
            "_yoast_wpseo_metadesc": "Произошла критическая ошибка при обработке",
            "image_caption": "Критическая ошибка",
            "focus_keyword": "ошибка"
        }
