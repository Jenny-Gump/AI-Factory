# LLM Response Formats Documentation

**Version**: 2.4.0 | **Date**: October 10, 2025

## Проблема решенная этим документом

**НИКОГДА БОЛЬШЕ НЕ ЧИНИТЬ ОДНО И ТО ЖЕ 10 РАЗ**

В функции `_parse_json_from_response` должна быть УМНАЯ логика определения правильного формата вместо тупого оборачивания всех объектов в массивы.

## Дефолтные форматы ответов по этапам

### 1. Ultimate Structure Creation (этап 7)
**Файл промпта**: `prompts/guides/02_create_ultimate_structure.txt`
**Ожидаемый формат**: ОБЪЕКТ
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

### 2. Extract Prompts (этап 6)
**Ожидаемый формат**: МАССИВ структур
```json
[
    {
        "section_title": "string",
        "section_order": number,
        "content_requirements": "string",
        "subsections": ["array"],
        "evidence_pack": "string"
    }
]
```
**Обработка**: Возвращать как есть если массив, оборачивать если одиночный объект.

### 3. Fact-Check (этап 10)
**Ожидаемый формат**: ИСПРАВЛЕННЫЙ HTML КОНТЕНТ (строка)
**Модель**: `gemini-2.5-flash` (с обязательным Google Search)
**⚠️ ВАЖНО**: Gemini может возвращать ответы в нескольких частях!
**⚠️ КРИТИЧНО**: ОБЯЗАТЕЛЬНО комбинировать ВСЕ части с "text"!

### 🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА: Gemini Multi-Part Responses

**Дата обнаружения**: 2025-09-30
**Симптомы**: Ответы обрезаются, содержат только 30-70% ожидаемого контента

**Причина**: Gemini API может возвращать ответ в нескольких частях (parts):
```json
{
  "candidates": [{
    "content": {
      "parts": [
        {"text": "Первая часть ответа..."},
        {"search_grounding": {...}},  // Результаты поиска Google
        {"text": "Вторая часть ответа..."},
        {"text": "Третья часть ответа..."}
      ]
    }
  }]
}
```

**❌ НЕПРАВИЛЬНО (старый код):**
```python
content = candidate["content"]["parts"][0]["text"]  # Только первая часть!
```

**✅ ПРАВИЛЬНО (новый код):**
```python
parts = candidate["content"]["parts"]
content_parts = []
for part in parts:
    if "text" in part:
        content_parts.append(part["text"])
content = "".join(content_parts)  # ВСЕ текстовые части
```

**Статистика фикса (реальные данные)**:
- Группа 2: было 5503 символа → стало 7312 символов (+33%)
- Группа 3: было 6634 символа → стало 8809 символов (+33%)
- Группа 4: было 6124 символа → стало 4994 символов (варьируется)

**Диагностика в логах**:
```
🔍 Gemini returned 7 part(s) in response  // Много частей!
📏 Total combined content: 7312 chars     // Размер после комбинирования
```

```html
<h2>Исправленный заголовок секции</h2>
<p>Исправленный контент с обновленными фактами, версиями, ссылками...</p>
<pre><code class='language-bash'>исправленные команды</code></pre>
<p>Дополнительная информация с <a href="https://source.com">проверенными ссылками</a></p>
```
**Обработка**: Возвращать как есть - чистый HTML контент секции.
**Цель**: Исправление фактических ошибок, устаревших данных, проверка ссылок.

### 4. Editorial Review
**Ожидаемый формат**: ОБЪЕКТ с метаданными
**Модель**: `deepseek-reasoner` (форматирование без fact-check)

```json
{
    "title": "string",
    "content": "HTML string",
    "excerpt": "string",
    "slug": "string",
    // ... другие мета-поля
}
```
**Обработка**: Возвращать как есть если имеет поля контента.

**Совместимость с API параметрами**:
- ✅ DeepSeek/Gemini: Поддерживают `response_format: {"type": "json_object"}`
- ❌ Perplexity: НЕ поддерживает `response_format` → 400 error
- ⚠️ Perplexity WEB SEARCH: Только модели с суффиксом `:online` выполняют поиск!

### 5. Link Processing
**Ожидаемый формат**: ОБЪЕКТ с планом ссылок
```json
{
    "link_plan": [
        {
            "anchor_text": "string",
            "query": "string",
            "section": "string",
            "ref_id": "string"
        }
    ]
}
```
**Обработка**: Извлекать `link_plan` массив.

## JSON Parsing Strategy (v2.4.0 Post-Processor Pattern)

### Modern Approach: Post-Processors

As of v2.4.0, JSON parsing is handled through the **Post-Processor Pattern** integrated into the Unified LLM Request System.

**Key Stages Using Post-Processors** (3/12):
1. `extract_sections` (stage 6) - Parses JSON array of section structures
2. `create_structure` (stage 7) - Parses ultimate structure JSON object
3. `editorial_review` (stage 12) - Parses WordPress metadata with repairs

**Why Post-Processors?**
- Automatic retry on JSON parsing failures
- Integrated with retry/fallback system
- Single place to handle parsing logic
- Consistent error handling

### Post-Processor Implementation

```python
def _extract_post_processor(response_text: str, model_name: str) -> List[Dict]:
    """
    Post-processor for extract_sections stage.

    Returns:
        Parsed list of dicts on success
        None on failure (triggers retry)
    """
    try:
        # Clean response (remove markdown, etc.)
        cleaned = clean_llm_tokens(response_text)

        # Parse JSON
        parsed = json.loads(cleaned)

        # Validate structure
        if not isinstance(parsed, list):
            logger.error("Expected list, got {type(parsed)}")
            return None  # Trigger retry

        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}")
        return None  # Trigger retry

# Usage in stage:
result, model = make_llm_request(
    stage_name="extract_sections",
    messages=messages,
    post_processor=_extract_post_processor  # ← Automatic retry on failure
)
# result is already parsed List[Dict]
```

### Retry Flow with Post-Processors

```
Attempt 1: API call → Response → Validation → Post-processor
                                                    ↓
                                              JSON parse fails
                                                    ↓
                                            Return None/raise
                                                    ↓
                                      RETRY (wait 2s)
                                                    ↓
Attempt 2: API call → Response → Validation → Post-processor
                                                    ↓
                                         JSON parse succeeds
                                                    ↓
                                         Return parsed result
```

**Benefits**:
- Parsing failures treated like any other error
- Automatic retry/fallback on JSON issues
- Consistent with rest of pipeline
- No special error handling needed

### Stages NOT Using Post-Processors

**Why not all stages?**

- **translation** (stage 9) - Returns plain text, no parsing needed
- **fact_check** (stage 10) - Returns HTML text, no parsing needed
- **generate_article** (stage 8) - Returns markdown, no parsing needed

Post-processors add complexity and should only be used when parsing/validation is necessary.

### Legacy Parsing (Deprecated)

**Old approach** (pre-v2.4.0):
```python
# ❌ DEPRECATED - Do not use
parsed = _parse_json_from_response(response)
if not parsed:
    # Manual retry logic...
```

**New approach** (v2.4.0+):
```python
# ✅ CURRENT - Use post-processor
result, model = make_llm_request(
    stage_name="my_stage",
    messages=messages,
    post_processor=my_post_processor  # Automatic retry
)
```

---

## Полная архитектура парсинга в _parse_json_from_response

### 6 ATTEMPTS UNIFIED SYSTEM (v2.4.0)

**Total Attempts**: 6 (3 Primary + 3 Fallback)

All stages now use the Unified LLM Request System with consistent retry/fallback logic:

**Primary Model**: 3 attempts with progressive backoff
- Attempt 1 → Fail → Wait 2s
- Attempt 2 → Fail → Wait 5s
- Attempt 3 → Fail → **FALLBACK**

**Fallback Model**: 3 attempts with progressive backoff
- Attempt 1 → Fail → Wait 2s
- Attempt 2 → Fail → Wait 5s
- Attempt 3 → Fail → **EXCEPTION**

**Validation**: Every attempt validated before considering success

### Example Log Output

```
🎯 [generate_article] Models to try: ['deepseek-reasoner', 'google/gemini-2.5-flash-lite']
🤖 [generate_article] Trying primary model: deepseek-reasoner
📝 [generate_article] Attempt 1/3 with deepseek-reasoner
✅ [generate_article] Success with deepseek-reasoner on attempt 1
```

**If primary fails**:
```
❌ [generate_article] Attempt 3 failed: Validation failed
🤖 [generate_article] Trying fallback model: google/gemini-2.5-flash-lite
📝 [generate_article] Attempt 1/3 with google/gemini-2.5-flash-lite
✅ [generate_article] Success with google/gemini-2.5-flash-lite on attempt 1
```

### Configuration

**File**: `src/config.py`

```python
LLM_MODELS = {
    "extract_sections": "deepseek-chat",           # Primary
    "create_structure": "deepseek-reasoner",       # Primary
    "generate_article": "deepseek-reasoner",       # Primary
    ...
}

FALLBACK_MODELS = {
    "extract_sections": "google/gemini-2.5-flash-lite-preview-06-17",  # Fallback
    "create_structure": "google/gemini-2.5-flash-lite-preview-06-17",  # Fallback
    "generate_article": "google/gemini-2.5-flash-lite-preview-06-17",  # Fallback
    ...
}

RETRY_CONFIG = {
    "max_attempts": 3,      # Per model
    "delays": [2, 5, 10]    # Progressive backoff (seconds)
}
```

**See**: [TECHNICAL.md](TECHNICAL.md) - Unified Request System details

---

### 5-Level JSON Parsing Fallback System

Функция `_parse_json_from_response()` использует 5-этапную систему парсинга с fallback логикой:

#### **Attempt 1: Standard JSON parsing**
- Стандартный `json.loads(response_content)`
- Быстрый и надежный для корректного JSON
- При успехе применяется SMART DETECTION LOGIC

#### **Attempt 1.5: Enhanced JSON preprocessing**
- Продвинутая предобработка для исправления LLM багов
- Множественные regex-фиксы перед парсингом
- **СПИСОК ВСЕХ ФИКСОВ**:
  ```python
  # DeepSeek model specific fixes
  fixed_content = re.sub(r'"context_after: "', r'"context_after": "', fixed_content)
  fixed_content = re.sub(r'"context_before: "', r'"context_before": "', fixed_content)
  fixed_content = re.sub(r'"anchor_text: "', r'"anchor_text": "', fixed_content)
  fixed_content = re.sub(r'"query: "', r'"query": "', fixed_content)
  fixed_content = re.sub(r'"hint: "', r'"hint": "', fixed_content)
  fixed_content = re.sub(r'"section: "', r'"section": "', fixed_content)
  fixed_content = re.sub(r'"ref_id: "', r'"ref_id": "', fixed_content)

  # Generic missing colons fix
  fixed_content = re.sub(r'"([^"]+): (["\[\{])', r'"\1": \2', fixed_content)

  # Control characters fix
  fixed_content = re.sub(r'(:\s*")([^"]*?)(")', lambda m: m.group(1) + m.group(2).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + m.group(3), fixed_content)

  # Escaped underscores fix
  fixed_content = fixed_content.replace('prompt\\_text', 'prompt_text')
  fixed_content = fixed_content.replace('expert\\_description', 'expert_description')
  fixed_content = fixed_content.replace('why\\_good', 'why_good')
  fixed_content = fixed_content.replace('how\\_to\\_improve', 'how_to_improve')
  fixed_content = re.sub(r'\\\\_', '_', fixed_content)

  # DeepSeek JSON array separator bug fix (НОВЫЙ)
  fixed_content = re.sub(r'\}],\s*\{', '}, {', fixed_content)

  # Unescaped quotes fix (сложная функция)
  # ... advanced quote fixing logic
  ```
- При успехе применяется SMART DETECTION LOGIC

#### **Attempt 2: Basic regex cleanup**
- Удаление лишних символов перед/после JSON
- `re.search(r'\[.*\]|\{.*\}', response_content, re.DOTALL)`

#### **Attempt 3: Markdown cleanup**
- Удаление markdown блоков ```json ... ```
- Извлечение JSON из текста

#### **Attempt 4: JSON extraction**
- Поиск JSON паттернов в тексте
- Попытка извлечь валидный JSON фрагмент

#### **Attempt 5: Final fallback**
- Возврат пустого массива `[]` при полном провале
- Логирование критической ошибки

### SMART DETECTION LOGIC

Применяется при успешном парсинге (Attempt 1 и 1.5):

1. **Если массив** → вернуть как есть
2. **Если объект с ключами `article_structure` + `writing_guidelines`** → Ultimate Structure → вернуть как есть
3. **Если объект с ключом `data`** → извлечь содержимое data
4. **Если объект с ключом `link_plan`** → извлечь содержимое link_plan
5. **Иначе одиночный объект структуры** → обернуть в массив для обратной совместимости

### Код SMART DETECTION:
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

## Тестовые случаи

### ✅ Правильная обработка Ultimate Structure
```json
INPUT:  {"article_structure": [...], "writing_guidelines": {...}}
OUTPUT: {"article_structure": [...], "writing_guidelines": {...}}  (БЕЗ оборачивания!)
```

### ✅ Правильная обработка массива структур
```json
INPUT:  [{"section_title": "..."}, {"section_title": "..."}]
OUTPUT: [{"section_title": "..."}, {"section_title": "..."}]  (Как есть)
```

### ✅ Правильная обработка одиночной структуры
```json
INPUT:  {"section_title": "..."}
OUTPUT: [{"section_title": "..."}]  (Обернуть в массив)
```

### ✅ Правильная обработка data wrapper
```json
INPUT:  {"data": [{"section_title": "..."}]}
OUTPUT: [{"section_title": "..."}]  (Извлечь data)
```

## Совместимость API параметров по моделям

### response_format поддержка:
- ✅ **DeepSeek**: Поддерживает `{"type": "json_object"}`
- ✅ **Gemini**: Поддерживает `{"type": "json_object"}`
- ❌ **Perplexity**: НЕ поддерживает `response_format` (400 error)

### Логика в llm_processing.py:
```python
# Only add response_format for non-perplexity models
current_model = model_name or LLM_MODELS.get(stage, DEFAULT_MODEL)
if not current_model.startswith("perplexity/"):
    request_params["response_format"] = {"type": "json_object"}
```

## При добавлении новых этапов

1. **Определить дефолтный формат** в промпте
2. **Проверить совместимость модели** с API параметрами
3. **Добавить detection rule** в функцию парсинга если нужна особая логика
4. **Обновить этот документ** с новым форматом
5. **Протестировать** на реальных данных

## Примеры LLM ошибок и их исправлений

### DeepSeek Specific Bugs:
1. **Missing colons**: `"key": "` → `"key": "`
2. **Array separator bug**: `}], {` → `}, {` (ИСПРАВЛЕНО)
3. **Escaped underscores**: `prompt\\_text` → `prompt_text`

### General JSON Issues:
1. **Control characters**: `\n`, `\r`, `\t` в строковых значениях
2. **Unescaped quotes**: Кавычки внутри HTML контента
3. **Malformed structure**: Отсутствующие запятые, скобки

### Markdown Wrapping:
- LLM оборачивают JSON в ```json ... ```
- Требуется извлечение из markdown блоков

---

## Post-Processor Examples

### Example 1: Extract Sections (JSON Array)

**Expected Format**:
```json
[
  {
    "section_title": "Introduction",
    "section_description": "Overview of the topic",
    "key_points": ["point1", "point2"]
  },
  ...
]
```

**Post-Processor**:
```python
def _extract_post_processor(response_text: str, model_name: str) -> List[Dict]:
    cleaned = clean_llm_tokens(response_text)

    try:
        parsed = json.loads(cleaned)

        # Validate structure
        if not isinstance(parsed, list):
            return None

        # Validate each section
        for section in parsed:
            if not isinstance(section, dict):
                return None
            if "section_title" not in section:
                return None

        return parsed

    except json.JSONDecodeError:
        return None
```

### Example 2: Editorial Review (Complex JSON with Repairs)

**Expected Format**:
```json
{
  "title": "Article Title",
  "content": "<p>HTML content</p>",
  "excerpt": "Summary",
  "slug": "article-slug",
  "_yoast_wpseo_title": "SEO title",
  ...
}
```

**Post-Processor with Repairs**:
```python
def _editorial_post_processor(response_text: str, model_name: str) -> Dict:
    # Try multiple JSON extraction strategies
    for attempt, strategy in enumerate(JSON_EXTRACTION_STRATEGIES):
        try:
            parsed = strategy(response_text)

            # Validate required fields
            required = ["title", "content", "excerpt"]
            if all(k in parsed for k in required):
                return parsed

        except Exception as e:
            logger.debug(f"Strategy {attempt} failed: {e}")
            continue

    # All strategies failed
    return None
```

### Example 3: Create Structure (Ultimate Structure)

**Expected Format**:
```json
{
  "title": "Article Title",
  "sections": [
    {
      "section_title": "Section 1",
      "subsections": [...]
    }
  ]
}
```

**Post-Processor**:
```python
def _structure_post_processor(response_text: str, model_name: str) -> Dict:
    cleaned = clean_llm_tokens(response_text)

    try:
        parsed = json.loads(cleaned)

        # Validate structure
        if not isinstance(parsed, dict):
            return None

        if "sections" not in parsed:
            return None

        if not isinstance(parsed["sections"], list):
            return None

        return parsed

    except json.JSONDecodeError:
        return None
```

---

## История изменений

- **2025-10-10**: v2.4.0 - Post-processor pattern, 6 attempts unified system
- **2025-09-24**: Создан документ после исправления проблемы с двойным оборачиванием ultimate_structure
- Исправлена логика в `_parse_json_from_response` для корректного определения форматов
- **2025-09-25**:
  - Добавлена документация по совместимости Perplexity моделей с response_format параметром
  - **КРИТИЧЕСКИЙ ФИКС**: Добавлен фикс DeepSeek JSON array separator bug `}], {` → `}, {`
  - Добавлена полная документация 5-этапной системы парсинга
  - Документированы все существующие фиксы в enhanced preprocessing
- **2025-10-01** (v2.1.4):
  - **КРИТИЧЕСКИЙ ФИКС**: Добавлена система детекции спама с character dominance анализом
  - **НОВАЯ ВАЛИДАЦИЯ**: Обнаружение контента без слов в длинных текстах
  - **РАСШИРЕННЫЙ СПИСОК**: Extended special characters для детекции спама
  - **ИНТЕГРАЦИЯ**: Валидация на всех LLM этапах для предотвращения брака
- **2025-09-30** (v2.1.2):
  - **TOKEN CLEANUP**: Система очистки служебных токенов LLM для предотвращения контаминации контекста