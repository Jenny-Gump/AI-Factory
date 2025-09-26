# LLM Response Formats Documentation

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

### 3. Fact-Check (этап 9)
**Ожидаемый формат**: ИСПРАВЛЕННЫЙ HTML КОНТЕНТ (строка)
**Модель**: `perplexity/sonar-reasoning-pro:online` (с обязательным web search)
**⚠️ ВАЖНО**: Perplexity модели НЕ поддерживают параметр `response_format`!
**⚠️ КРИТИЧНО**: Для веб-поиска ОБЯЗАТЕЛЬНО использовать суффикс `:online`!

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
**Модель**: `deepseek/deepseek-chat-v3.1:free` (форматирование без fact-check)

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

## Полная архитектура парсинга в _parse_json_from_response

### 5 ATTEMPTS SYSTEM

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

## История изменений

- **2025-09-24**: Создан документ после исправления проблемы с двойным оборачиванием ultimate_structure
- Исправлена логика в `_parse_json_from_response` для корректного определения форматов
- **2025-09-25**:
  - Добавлена документация по совместимости Perplexity моделей с response_format параметром
  - **КРИТИЧЕСКИЙ ФИКС**: Добавлен фикс DeepSeek JSON array separator bug `}], {` → `}, {`
  - Добавлена полная документация 5-этапной системы парсинга
  - Документированы все существующие фиксы в enhanced preprocessing