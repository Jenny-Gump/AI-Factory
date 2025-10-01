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

## Content Quality Validation

### 🛡️ SPAM DETECTION SYSTEM (v2.1.4)

**Проблема**: LLM может возвращать спам-контент (символы-повторения, зацикливание)
**Симптомы**: Секции содержат "----", "....", "1.1.1.1...", бесконечные повторения
**Решение**: Многоуровневая валидация качества контента на всех LLM этапах

#### Проверки качества в validate_content_quality():

```python
def validate_content_quality(content: str, min_length: int = 50) -> bool:
    # 1. Минимальная длина контента
    if len(content.strip()) < min_length:
        return False

    # 2. Single character dominance detection (НОВАЯ ПРОВЕРКА v2.1.4)
    if len(content) > 100:
        char_counts = {}
        for char in content:
            if not char.isspace():
                char_counts[char] = char_counts.get(char, 0) + 1

        if char_counts:
            most_frequent_char = max(char_counts, key=char_counts.get)
            most_frequent_count = char_counts[most_frequent_char]
            char_dominance = most_frequent_count / len(content.replace(' ', '').replace('\n', '').replace('\t', ''))

            # >70% одного символа = спам
            if char_dominance > 0.7:
                logger.warning(f"Content validation failed: single character dominance ({most_frequent_char}: {char_dominance:.1%})")
                return False

    # 3. No words in long content (НОВАЯ ПРОВЕРКА v2.1.4)
    words = re.findall(r'\b[a-zA-Zа-яА-Я]{2,}\b', content)
    if len(words) == 0 and len(content) > 100:
        logger.warning("Content validation failed: no words found in long content")
        return False

    # 4. Повторяющиеся паттерны (>40% одинаковых подстрок)
    # 5. Зацикливание точек/цифр (10+ подряд)
    # 6. Уникальность слов (<15% уникальных = спам)
    # 7. Extended special characters detection (ОБНОВЛЕНА v2.1.4)
    special_chars = '.,!?;:()[]{}=-_*+#@$%^&|\\/<>`~"\'…—–'
```

#### Extended Spam Character List (v2.1.4):
- **Дефисы**: `-`, `—`, `–`
- **Подчеркивания**: `_`
- **Точки и спецсимволы**: `.`, `*`, `+`, `#`, `@`, `$`, `%`, `^`, `&`
- **Кавычки**: `"`, `'`, `…`

#### Integration Points:
```python
# После очистки токенов на всех LLM этапах
section_content = clean_llm_tokens(section_content)
if not validate_content_quality(section_content, min_length=50):
    # Retry или fallback на другую модель
    logger.warning(f"Content validation failed for stage {stage}")
    return None
```

#### Применяется на этапах:
- **Этап 7**: Извлечение структур (`extract_prompts`)
- **Этап 8**: Создание ультимативной структуры
- **Этап 9**: Посекционная генерация (sync + async)
- **Этап 9.5**: Факт-чекинг секций
- **Этап 10**: Редакторская обработка

#### Результат валидации:
- ✅ Автоматическое обнаружение спама типа "----" (99.7% точность)
- ✅ Graceful retry при обнаружении брака
- ✅ Блокировка контента без слов
- ✅ Подробное логирование причин отклонения

### 🧹 LLM TOKEN CONTAMINATION FIX (v2.1.2)

**Проблема**: Служебные токены LLM попадали в контекст следующих секций
**Симптом**: Модель "забывает" тему из-за токена `<｜begin▁of▁sentence｜>`
**Решение**: Автоматическая очистка всех служебных токенов

#### Функция clean_llm_tokens():
```python
def clean_llm_tokens(text: str) -> str:
    """Remove LLM-specific tokens from generated content."""
    tokens_to_remove = [
        '<｜begin▁of▁sentence｜>',
        '<|begin_of_sentence|>',
        '<｜end▁of▁sentence｜>',
        '<|end_of_sentence|>',
        '<|im_start|>', '<|im_end|>',
        '<|end|>', '<<SYS>>', '<</SYS>>',
        '[INST]', '[/INST]'
    ]
    # Удаляем все служебные токены из текста
```

#### Integration:
```python
# После каждого ответа от LLM
section_content = response_obj.choices[0].message.content
section_content = clean_llm_tokens(section_content)  # ← ОБЯЗАТЕЛЬНО
```

## История изменений

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