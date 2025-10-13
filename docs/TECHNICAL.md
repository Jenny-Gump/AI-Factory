# Content Factory - Техническая документация

Детальная техническая документация архитектуры, API интеграций, и внутреннего устройства Content Factory.

---

## 📋 Содержание

1. [Конфигурация](#конфигурация)
2. [Архитектура пайплайна](#архитектура-пайплайна)
3. [LLM Integration](#llm-integration)
4. [WordPress Integration](#wordpress-integration)
5. [Производительность](#производительность)

---

## ⚙️ Конфигурация

### API Ключи

Все API ключи хранятся в `.env` файле в корне проекта.

#### Обязательные ключи

```bash
# Firecrawl - поиск и парсинг контента
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# OpenRouter - доступ к DeepSeek FREE и Gemini
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx

# Google Gemini - ОБЯЗАТЕЛЬНО для fact-check с веб-поиском
GEMINI_API_KEY=AIzaSyAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### Опциональные ключи

```bash
# DeepSeek Direct - прямой доступ (не обязательно)
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# WordPress - для автоматической публикации
WORDPRESS_URL=https://your-site.com
WORDPRESS_USERNAME=your_username
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### Модели LLM

Конфигурация в `src/config.py`:

```python
LLM_MODELS = {
    "extract_sections": "deepseek-reasoner",
    "create_structure": "deepseek-reasoner",
    "generate_article": "deepseek-reasoner",
    "fact_check": "gemini-2.5-flash-preview-09-2025",  # Native web search
    "link_placement": "gemini-2.5-flash-preview-09-2025",  # Native web search
    "translation": "deepseek-reasoner",
    "editorial_review": "deepseek-reasoner",
}
```

### Fallback модели

Автоматическое переключение при сбоях:

```python
FALLBACK_MODELS = {
    "extract_sections": "google/gemini-2.0-flash-001",
    "create_structure": "google/gemini-2.0-flash-001",
    "generate_article": "google/gemini-2.0-flash-001",
    "fact_check": "gemini-2.5-flash",  # Stable Gemini 2.5 Flash with web search
    "link_placement": "gemini-2.5-flash",  # Stable Gemini 2.5 Flash with web search
    "translation": "google/gemini-2.0-flash-001",
    "editorial_review": "google/gemini-2.0-flash-001",
}
```

### Провайдеры LLM

```python
LLM_PROVIDERS = {
    "deepseek-reasoner": "deepseek",
    "google/gemini-2.0-flash-001": "openrouter",
    "gemini-2.5-flash-preview-09-2025": "google_direct",  # Direct Gemini API
}
```

### Параметры производительности

```python
# Firecrawl
CONCURRENT_REQUESTS = 5          # Параллельные запросы
MIN_CONTENT_LENGTH = 10000       # Минимальная длина контента
TOP_N_SOURCES = 5                # Количество источников

# Таймауты
SECTION_TIMEOUT = 180            # 3 минуты на секцию
MODEL_TIMEOUT = 60               # 1 минута на LLM запрос
SECTION_MAX_RETRIES = 3          # Retry попытки

# Веса оценки источников
TRUST_SCORE_WEIGHT = 0.5
RELEVANCE_SCORE_WEIGHT = 0.3
DEPTH_SCORE_WEIGHT = 0.2
```

---

## 🏗️ Архитектура пайплайна

### Полная схема потока данных

```
USER INPUT: "тема статьи"
    ↓
[1] Search → 20 URLs
    ↓
[2] Scrape → 18-19 raw content
    ↓
[3] Score → Ranked sources
    ↓
[4] Select → Top 5 sources
    ↓
[5] Clean → Clean text (5× ~10k chars)
    ↓
[6] Extract Prompts → 5 structures
    ↓
[7] Create Ultimate Structure → 1 combined structure
    ↓
[8] Generate Sections → Section-by-section generation (Russian)
    ↓
[9] Translation → Section-by-section translation to target language
    ↓
[10] Fact-Check → Gemini web search validation (on translated text)
    ↓
[11] Link Placement → 10-20 external links (for target language)
    ↓
[12] Editorial Review → WordPress optimized + Publication
```

### Детальные этапы

#### Этап 1: Search (Firecrawl Search API)

**API**: `POST https://api.firecrawl.dev/v2/search`

```python
{
    "query": "user topic",
    "limit": 20
}
```

**Ответ**:
```json
[
    {
        "url": "https://example.com/article",
        "title": "Article Title",
        "description": "Description"
    }
]
```

#### Этап 2: Scrape (Firecrawl Scrape API)

**API**: `POST https://api.firecrawl.dev/v0/scrape`

```python
{
    "url": "https://example.com",
    "formats": ["markdown"],
    "onlyMainContent": true
}
```

**Обработка**:
- Параллельные запросы (max 5 одновременно)
- Retry логика при таймаутах
- Успешность: ~95% (18-19 из 20)

#### Этап 10: Fact-Check (Google Gemini Direct API)

**Уникальность**: Прямое обращение к Google Generative AI API с нативным веб-поиском.

**API**: `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent`

**Запрос**:
```json
{
    "contents": [{"role": "user", "parts": [{"text": "prompt"}]}],
    "generationConfig": {"temperature": 0.3},
    "tools": [{
        "googleSearch": {}  // Native web search
    }]
}
```

**Особенность**: Multi-part responses

Gemini может возвращать ответ в нескольких частях:

```json
{
    "candidates": [{
        "content": {
            "parts": [
                {"text": "First part"},
                {"search_grounding": {...}},
                {"text": "Second part"},
                {"text": "Third part"}
            ]
        }
    }]
}
```

**Обработка**:
```python
# CRITICAL: Combine ALL text parts
parts = candidate["content"]["parts"]
content_parts = []
for part in parts:
    if "text" in part:
        content_parts.append(part["text"])
content = "".join(content_parts)
```

#### Этап 11: Link Placement

**Процесс**:
1. LLM анализирует контент и создает план ссылок (10-20 позиций)
2. Firecrawl Search API ищет кандидатов по запросам
3. Фильтрация источников (блокировка reddit, medium, stackoverflow)
4. Умная вставка маркеров [1], [2], [3] с коррекцией позиций
5. Создание раздела "Полезные ссылки"

**Приоритет источников**:
1. docs.* (официальная документация)
2. arxiv.org (научные статьи)
3. github.com (репозитории)
4. Корпоративные блоги

#### Этап 9: Translation (Section-by-Section)

**Процесс**:
1. Перевод каждой секции отдельно (как генерация)
2. Валидация качества через regex (300+ chars)
3. Словарная проверка через pyenchant
4. Сохранение метаданных (оригинал, модель, язык)

**Output**:
```json
{
    "section_num": 1,
    "section_title": "Introduction",
    "content": "Translated content...",
    "status": "translated",
    "original_content": "Исходный контент...",
    "translation_model": "deepseek-reasoner",
    "target_language": "english"
}
```

#### Этап 12: Editorial Review

**Retry система**: 3×3 = 9 попыток максимум

```python
for model_attempt in range(3):      # 3 модели
    for retry in range(3):           # 3 попытки
        try:
            response = llm_request()
            if valid(response):
                return response
        except:
            wait(2^retry seconds)  # Exponential backoff
```

**JSON нормализация**: 4-уровневая система

1. Standard JSON parsing
2. Enhanced preprocessing (regex fixes)
3. Markdown cleanup
4. JSON extraction fallback

---

## 🤖 LLM Integration

### Response Formats

LLM модели возвращают разные форматы данных в зависимости от этапа.

#### Format 1: Ultimate Structure (этап 7)

**Ожидаемый формат**: ОБЪЕКТ (не массив!)

```json
{
    "article_structure": [
        {
            "section_title": "string",
            "section_order": number,
            "section_description": "string",
            "content_requirements": "string",
            "estimated_length": "string",
            "subsections": ["array"],
            "evidence_pack": "string"
        }
    ],
    "writing_guidelines": {
        "target_audience": "string",
        "tone_and_style": "string",
        "key_messaging": "string",
        "call_to_action": "string"
    }
}
```

**Обработка**: Возвращать КАК ЕСТЬ, НЕ оборачивать в массив!

#### Format 2: Extract Prompts (этап 6)

**Ожидаемый формат**: МАССИВ структур

```json
[
    {
        "section_title": "string",
        "section_order": number,
        "content_requirements": "string",
        "subsections": ["array"],
        "evidence_pack": "string",
        "section_length (symbols)": number
    }
]
```

#### Format 3: Translation (этап 9)

**Ожидаемый формат**: МАССИВ переведенных секций

```json
[
    {
        "section_num": 1,
        "section_title": "Introduction",
        "content": "Translated content...",
        "status": "translated",
        "original_content": "Исходный контент...",
        "translation_model": "deepseek-reasoner",
        "target_language": "english"
    }
]
```

#### Format 4: Fact-Check (этап 10)

**Ожидаемый формат**: ИСПРАВЛЕННЫЙ HTML КОНТЕНТ (строка)

```html
<h2>Исправленный заголовок</h2>
<p>Контент с обновленными фактами и <a href="url">ссылками</a></p>
<pre><code class='language-bash'>исправленные команды</code></pre>
```

#### Format 5: Editorial Review (этап 12)

**Ожидаемый формат**: ОБЪЕКТ с метаданными

```json
{
    "title": "string",
    "content": "HTML string",
    "excerpt": "string",
    "slug": "string",
    "meta_description": "string",
    "focus_keyphrase": "string"
}
```

### JSON Parsing Logic

**SMART DETECTION** в `_parse_json_from_response()`:

```python
if isinstance(parsed, dict):
    # Ultimate structure detection
    if "article_structure" in parsed and "writing_guidelines" in parsed:
        return parsed  # НЕ ОБОРАЧИВАЕМ!

    # Data wrapper detection
    elif "data" in parsed:
        return parsed["data"]

    # Link plan detection
    elif "link_plan" in parsed:
        return parsed["link_plan"]

    # Single structure - wrap for compatibility
    else:
        return [parsed]
```

### Content Quality Validation v3.0

**Функция**: `validate_content_quality_v3(content, min_length=300, target_language=None, finish_reason=None) -> tuple`

**Революционное обновление** (октябрь 6, 2025):
- Замена regex системы на научно-обоснованную многоуровневую валидацию
- Устранение критических пропусков спама (section_4, group_2 MAX_TOKENS)
- Возвращает кортеж: `(success: bool, reason: str)` для детальной диагностики

**Архитектура v3.0**:
- Валидация происходит ВНУТРИ `_make_llm_request_with_retry_sync()`
- Провал валидации → exception с детальной причиной → retry → fallback модель
- Единый порог: `min_length=300` для всех этапов
- **Новое**: передача `target_language` для языковой проверки
- **Новое**: проверка `finish_reason` от API для отклонения MAX_TOKENS/CONTENT_FILTER

**6 научно-обоснованных уровней проверки**:

1. **Compression Ratio (gzip)** - главная защита
   - Threshold: >4.0 = spam (Go Fish Digital, 2024)
   - Ловит все типы повторений (от 1 символа)
   - section_4: ratio 53.39 → BLOCKED ✅
   - group_2: ratio 129.97 → BLOCKED ✅

2. **Shannon Entropy** - информационная плотность
   - Threshold: <2.5 bits = repetitive content
   - Качественный текст: 3.5-4.5 bits

3. **Character Bigrams** - короткие циклы
   - Threshold: <15% unique bigrams
   - Защита от "-о-о-о-" паттернов (пропускал старый regex)

4. **Word Density** - лексическая структура
   - Valid range: 5-40% слов от текста
   - Отклоняет symbol spam

5. **Finish Reason** - API статус (НОВОЕ)
   - Accepted: STOP, END_TURN
   - Rejected: MAX_TOKENS, CONTENT_FILTER, ERROR
   - Защита от group_2 MAX_TOKENS спама ✅

6. **Language Check** - целевой язык (НОВОЕ)
   - **Russian**: >30% cyrillic characters
   - **English/Spanish/German/French**: >50% latin characters
   - **Unknown languages**: skip check (только 5 уровней)
   - Отклоняет fake words gibberish (ююю, язяк, цылеют) ✅
   - Отклоняет контент на неправильном языке ✅

**Применяется на этапах**:

**v3.0 валидация (6 уровней)**:
- **Этап 8** (generate_article): v3.0 full с `target_language=None`
- **Этап 9** (translation): v3.0 full + language check с `target_language` из `--language` флага
  - Поддерживаемые: `ru/russian/русский`, `en/english/английский`, `es/spanish/español/испанский`, `de/german/deutsch/немецкий`, `fr/french/français/французский`

**Минимальная валидация** (только длина ≥ 100 символов):
- **create_structure**: JSON структуры → низкий bigram uniqueness → false positives
- **Этап 7** (extract_sections): JSON структуры → низкий bigram uniqueness → false positives
- **Этап 10** (fact_check): короткие фактические ответы
- **Этап 11** (link_placement): HTML с ссылками → низкий bigram uniqueness
- **Этап 12** (editorial_review): контент уже проверен на этапах 8+9 → избыточная валидация

**Retry Flow v3.0**:
```
Primary model (3 попытки с v3.0 validation)
  → Fallback model (3 попытки с v3.0 validation)
  = 6 attempts total
```

**Научные источники**:
- Compression ratio: Go Fish Digital (2024) - SEO spam detection
- Shannon entropy: Stanford NLP (2024) - text diversity
- Kolmogorov complexity: Frontiers Psychology (2022)

**См. также**: [CONTENT_VALIDATION.md](CONTENT_VALIDATION.md) - полная документация v3.0

---

## Unified LLM Request System v2.4.0

### Architecture Overview

The Unified LLM Request System (`src/llm_request.py`) is the central orchestrator for ALL LLM API calls in the pipeline. Introduced in v2.3.2 and optimized in v2.4.0, it provides:

- **Single Entry Point**: All stages use `make_llm_request()`
- **Automatic Retry**: 3 attempts per model with progressive backoff [2s, 5s, 10s]
- **Automatic Fallback**: Primary → Fallback model on exhaustion
- **Unified Validation**: v3.0 multi-level validation on every attempt
- **Post-Processor Support**: Automatic retry on JSON parsing failures
- **Provider Routing**: DeepSeek Direct, Google Direct, OpenRouter
- **Token Tracking**: Integrated usage tracking across all stages
- **Response Saving**: Debug artifacts for all attempts

### Core Components

#### 1. LLMRequestHandler Class

**Location**: `src/llm_request.py:44-493`

**Key Methods**:
```python
class LLMRequestHandler:
    def __init__(self):
        self.provider_router = get_provider_router()
        self.validator = LLMResponseValidator()

    def make_request(
        self,
        stage_name: str,
        messages: List[Dict[str, str]],
        validation_level: str = "minimal",
        post_processor: Optional[Callable] = None,
        **kwargs
    ) -> Tuple[Any, str]:
        # Orchestrates: retry → fallback → validation → post-processing
        # Returns: (processed_result, actual_model_used)
```

**Dependencies**:
- `LLMProviderRouter` - Routes to appropriate API (DeepSeek, Google, OpenRouter)
- `LLMResponseValidator` - v3.0 validation system
- `TokenTracker` - Usage tracking (optional)

#### 2. Retry/Fallback Flow

**Total Attempts**: 6 (3 primary + 3 fallback)

**Flow Diagram**:
```
make_llm_request(stage_name, messages, ...)
  │
  ├─> Try Primary Model (from LLM_MODELS[stage_name])
  │   ├─> Attempt 1 → API call → Validate → Post-process
  │   │   ├─ Success → Return result
  │   │   └─ Fail → Wait 2s
  │   ├─> Attempt 2 → API call → Validate → Post-process
  │   │   ├─ Success → Return result
  │   │   └─ Fail → Wait 5s
  │   └─> Attempt 3 → API call → Validate → Post-process
  │       ├─ Success → Return result
  │       └─ Fail → FALLBACK
  │
  └─> Try Fallback Model (from FALLBACK_MODELS[stage_name])
      ├─> Attempt 1 → API call → Validate → Post-process
      │   ├─ Success → Return result
      │   └─ Fail → Wait 2s
      ├─> Attempt 2 → API call → Validate → Post-process
      │   ├─ Success → Return result
      │   └─ Fail → Wait 5s
      └─> Attempt 3 → API call → Validate → Post-process
          ├─ Success → Return result
          └─ Fail → Raise Exception
```

**Progressive Backoff**: [2s, 5s, 10s] between retries

#### 3. Validation Integration

Every API response is validated BEFORE considering success:

```python
# After API call succeeds:
is_valid = self.validator.validate(
    response_text=response_text,
    validation_level=validation_level,  # "v3", "minimal", "none", or custom
    custom_validator=custom_validator,
    **validation_kwargs
)

if not is_valid:
    # Triggers retry (same as API error)
    raise ValueError("Response validation failed")
```

**Validation Levels**:
- `"v3"` - Full 6-level scientific validation (default for generate_article)
- `"minimal"` - Length check only (default for most stages)
- `"none"` - No validation
- Custom validator function

See [CONTENT_VALIDATION.md](CONTENT_VALIDATION.md) for validation details.

#### 4. Post-Processor Pattern

**Purpose**: Automatic retry on JSON parsing or downstream validation failures

**Usage**:
```python
def my_post_processor(response_text: str, model_name: str) -> Any:
    """
    Parse/validate response. Return result or None to trigger retry.

    Returns:
        Processed result (dict, list, etc.) on success
        None on failure (triggers retry/fallback)

    Raises:
        Exception on failure (also triggers retry/fallback)
    """
    try:
        parsed = json.loads(response_text)
        # Additional validation here
        return parsed
    except Exception as e:
        logger.error(f"Post-processing failed: {e}")
        return None  # Triggers retry

# Use in request:
result, model = make_llm_request(
    stage_name="extract_sections",
    messages=messages,
    post_processor=my_post_processor
)
# result is already parsed/validated
```

**Stages Using Post-Processors** (3/12):
1. **extract_sections** (stage 6) - JSON array parsing
2. **create_structure** (stage 7) - JSON object parsing
3. **editorial_review** (stage 12) - Complex JSON with repairs

**Why Only 3 Stages?**
- Other stages return plain text (no parsing needed)
- Translation/fact-check return validated text directly
- Post-processors add complexity, only used when necessary

#### 5. Provider Routing

**File**: `src/llm_providers.py`

**Supported Providers**:
1. **DeepSeek Direct** - deepseek-reasoner, deepseek-chat
2. **Google Direct** - gemini-2.5-flash (with native web search)
3. **OpenRouter** - All other models (free DeepSeek, Google, etc.)

**Provider Selection Logic**:
```python
# Automatic based on model name:
"deepseek-reasoner" → DeepSeek Direct API
"gemini-2.5-flash" → Google Direct API (with grounding)
"google/gemini-*" → OpenRouter
"deepseek-chat" → OpenRouter (free)
```

**Benefits**:
- DeepSeek Direct: Lower latency, native JSON mode
- Google Direct: Native web search for fact-checking
- OpenRouter: Access to free models

#### 6. Token Tracking

**Integration**:
```python
# Automatic tracking when token_tracker provided:
make_llm_request(
    stage_name="generate_article",
    messages=messages,
    token_tracker=self.token_tracker  # TokenTracker instance
)

# Tracks:
# - Input tokens
# - Output tokens
# - Model used
# - Provider
# - Attempt number
# - Stage name
```

**Report Generated**: `output/{topic}/token_usage_report.json`

#### 7. Response Saving

**All responses saved** for debugging:

**Successful responses**:
```
output/{topic}/{stage}/llm_responses_raw/
  └─ {stage}_response_attempt{N}_{timestamp}.txt
```

**Failed responses**:
```
output/{topic}/{stage}/llm_responses_raw/
  └─ ERROR_{stage}_response_attempt{N}_{timestamp}.txt
```

**Contents**:
- Timestamp
- Model name
- Attempt number
- Validation status
- Full response text

### Configuration

**File**: `src/config.py`

```python
# Primary models (first choice)
LLM_MODELS = {
    "extract_sections": "deepseek-chat",
    "create_structure": "deepseek-reasoner",
    "generate_article": "deepseek-reasoner",
    "translation": "deepseek-reasoner",
    "fact_check": "gemini-2.5-flash-preview-09-2025",
    "editorial_review": "deepseek-reasoner"
}

# Fallback models (second choice)
FALLBACK_MODELS = {
    "extract_sections": "google/gemini-2.0-flash-001",
    "create_structure": "google/gemini-2.0-flash-001",
    "generate_article": "google/gemini-2.0-flash-001",
    "translation": "google/gemini-2.0-flash-001",
    "fact_check": "gemini-2.5-flash",
    "editorial_review": "google/gemini-2.0-flash-001"
}

# Retry configuration
RETRY_CONFIG = {
    "max_attempts": 3,      # Per model
    "delays": [2, 5, 10]    # Progressive backoff (seconds)
}
```

### Benefits

1. **Single Source of Truth** - All retry/fallback logic in one place
2. **Consistent Behavior** - All stages use same retry/fallback flow
3. **Easy to Update** - Change retry logic once, applies everywhere
4. **Better Debugging** - Centralized logging and response saving
5. **Reduced Code** - No duplicate retry logic across stages
6. **Extensible** - Easy to add new validation levels or post-processors

### Migration from Old System

**Before v2.3.2**:
- Each stage had its own retry logic
- Inconsistent retry counts (some 3, some 5)
- Different validation approaches
- Manual fallback handling

**After v2.4.0**:
- All stages use `make_llm_request()`
- Consistent 6 attempts (3 primary + 3 fallback)
- Unified v3.0 validation
- Automatic fallback on exhaustion

### Related Documentation

- [CONTENT_VALIDATION.md](CONTENT_VALIDATION.md) - v3.0 validation system details
- [BATCH_SYSTEM.md](BATCH_SYSTEM.md) - Batch processing integration
- [flow.md](flow.md) - Complete pipeline with unified system integration
- [config.md](config.md) - Model configuration and retry settings

---

### Token Cleanup

**Функция**: `clean_llm_tokens(text)`

Удаление служебных токенов LLM:

```python
tokens_to_remove = [
    '<｜begin▁of▁sentence｜>',
    '<|begin_of_sentence|>',
    '<｜end▁of▁sentence｜>',
    '<|end_of_sentence|>',
    '<|im_start|>', '<|im_end|>',
    '<|end|>', '<<SYS>>', '<</SYS>>',
    '[INST]', '[/INST]'
]
```

**Применяется**: После КАЖДОГО ответа от LLM.

---

## 🌐 WordPress Integration

### REST API Endpoints

#### Создание поста

```http
POST /wp-json/wp/v2/posts
Authorization: Basic base64(username:app_password)

{
    "title": "Post Title",
    "content": "HTML content",
    "excerpt": "Post excerpt",
    "status": "draft",
    "categories": [825],
    "meta": {
        "yoast_wpseo_title": "SEO Title",
        "yoast_wpseo_metadesc": "Meta Description",
        "yoast_wpseo_focuskw": "Focus Keyword"
    }
}
```

#### Yoast SEO Meta

```http
POST /wp-json/custom-yoast/v1/update-meta/{post_id}
Authorization: Basic base64(username:app_password)

{
    "yoast_wpseo_title": "SEO Title",
    "yoast_wpseo_metadesc": "Description",
    "yoast_wpseo_focuskw": "keyword"
}
```

### Форматирование контента

#### Code blocks fix

WordPress `wpautop` ломает `<pre>` блоки с реальными newlines.

**Решение**: Функция `fix_content_newlines()`

```python
def fix_content_newlines(content):
    # Replace newlines in <pre><code> blocks with <br>
    pattern = r'(<pre[^>]*>)(<code[^>]*>)(.*?)(</code>)(</pre>)'

    def fix_code_block(match):
        pre_tag, code_opening, code_content, code_closing, pre_closing = match.groups()
        fixed_content = code_content.replace('\n', '<br>')
        return f"{pre_tag}{code_opening}{fixed_content}{code_closing}{pre_closing}"

    return re.sub(pattern, fix_code_block, content, flags=re.DOTALL)
```

#### Markdown to HTML

```python
def _convert_markdown_to_html(content):
    # Convert markdown code blocks to HTML
    pattern = r'```(\w+)?\n(.*?)```'

    def convert_code_block(match):
        language, code = match.groups()
        lang_class = f' class="language-{language}"' if language else ''
        return f'<pre><code{lang_class}>{code}</code></pre>'

    return re.sub(pattern, convert_code_block, content, flags=re.DOTALL)
```

---

## ⚡ Производительность

### Время выполнения по этапам

```
Этап 1-5:  ~2-3 мин    (Сбор данных)
Этап 6-8:  ~3-4 мин    (Структурирование)
Этап 9:    ~2-3 мин    (Генерация секций)
Этап 10:   ~2-3 мин    (Fact-check)
Этап 11:   ~1-2 мин    (Link placement)
Этап 12:   ~1 мин      (Translation)
Этап 13:   ~1-2 мин    (Editorial review)
Этап 14:   ~10 сек     (Publication)

ИТОГО:     ~12-17 мин
```

### Использование токенов

```
Этап 6:    ~5-8k tokens     (Extract prompts)
Этап 7:    ~3-5k tokens     (Ultimate structure)
Этап 8-9:  ~25-35k tokens   (Generate article)
Этап 10:   ~10-15k tokens   (Fact-check)
Этап 11:   ~3-5k tokens     (Link placement)
Этап 12:   ~2-4k tokens     (Translation)
Этап 13:   ~3-5k tokens     (Editorial review)

ИТОГО:     ~45-55k tokens
```

### Batch Processing Optimization

**Оптимизация памяти** (`batch_config.py`):

```python
MEMORY_CLEANUP = {
    "force_gc_between_topics": True,      # gc.collect()
    "clear_llm_caches": True,             # Clear OpenAI clients
    "reset_token_tracker": True,          # Reset tracker
    "close_http_connections": True,       # Force cleanup
    "clear_firecrawl_cache": True,        # Clear cache
}

BATCH_CONFIG = {
    "max_memory_mb": 2048,                # 2GB limit
    "max_concurrent_requests": 5,
    "retry_failed_topics": 2,
    "retry_delay_seconds": 60,
}
```

**Мониторинг**:
- Проверка каждые 5 минут
- Предупреждение при >1.8GB
- Автоматическая очистка между темами

---

## 🔧 Диагностика проблем

### Система сохранения сырых ответов LLM

Все запросы/ответы LLM автоматически сохраняются:

```
output/{topic}/{stage}/
├── llm_requests/
│   └── request_{timestamp}.txt
└── llm_responses_raw/
    └── response_{timestamp}.txt
```

### Метод диагностики

1. **Начни с сырых данных**: Читай `llm_responses_raw/*.txt`
2. **Проверь цепочку**: Смотри что входит → что выходит на каждом этапе
3. **Найди точку сбоя**: Где ИМЕННО данные меняются неожиданно
4. **Проверь промпт**: Читай промпты которые идут в LLM
5. **Исправь источник**: Промпт или код парсинга

**НЕ предполагать - ПРОВЕРЯТЬ ФАКТЫ!**

---

## 📚 Дополнительная документация

- **[GUIDE.md](GUIDE.md)** - Руководство пользователя
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - FAQ и решение проблем
- **[config.md](config.md)** - Полный справочник конфигурации
- **[../CHANGELOG.md](../CHANGELOG.md)** - История версий

---

**Версия**: 2.4.0 | **Статус**: ✅ Production Ready
