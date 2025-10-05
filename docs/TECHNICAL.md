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
    "extract_prompts": "deepseek/deepseek-chat-v3.1:free",
    "create_structure": "deepseek/deepseek-chat-v3.1:free",
    "generate_article": "deepseek/deepseek-chat-v3.1:free",
    "fact_check": "gemini-2.5-flash-preview-09-2025",  # Native web search
    "link_placement": "gemini-2.5-flash-preview-09-2025",  # Native web search
    "translation": "deepseek/deepseek-chat-v3.1:free",
    "editorial_review": "deepseek/deepseek-chat-v3.1:free",
}
```

### Fallback модели

Автоматическое переключение при сбоях:

```python
FALLBACK_MODELS = {
    "extract_prompts": "google/gemini-2.5-flash-lite-preview-06-17",
    "create_structure": "google/gemini-2.5-flash-lite-preview-06-17",
    "generate_article": "google/gemini-2.5-flash-lite-preview-06-17",
    "fact_check": "gemini-2.5-flash",  # Stable Gemini 2.5 Flash with web search
    "link_placement": "google/gemini-2.5-flash-lite-preview-06-17",
    "translation": "google/gemini-2.5-flash-lite-preview-06-17",
    "editorial_review": "google/gemini-2.5-flash-lite-preview-06-17",
}
```

### Провайдеры LLM

```python
LLM_PROVIDERS = {
    "deepseek/deepseek-chat-v3.1:free": "openrouter",
    "google/gemini-2.5-flash-lite-preview-06-17": "openrouter",
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
[8] Generate Article → Generated content
    ↓
[9] Generate Sections → Section-by-section generation
    ↓
[10] Fact-Check → Gemini web search validation
    ↓
[11] Link Placement → 10-20 external links
    ↓
[12] Translation → Target language (default: русский)
    ↓
[13] Editorial Review → WordPress optimized
    ↓
[14] WordPress Publication → Published draft
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

#### Этап 13: Editorial Review

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
        "evidence_pack": "string"
    }
]
```

#### Format 3: Fact-Check (этап 10)

**Ожидаемый формат**: ИСПРАВЛЕННЫЙ HTML КОНТЕНТ (строка)

```html
<h2>Исправленный заголовок</h2>
<p>Контент с обновленными фактами и <a href="url">ссылками</a></p>
<pre><code class='language-bash'>исправленные команды</code></pre>
```

#### Format 4: Editorial Review (этап 13)

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

### Content Quality Validation

**Функция**: `validate_content_quality(content, min_length=50)`

**Проверки**:
1. Минимальная длина (50+ символов)
2. Single character dominance (>70% одного символа = спам)
3. No words in long content (контент без слов)
4. Повторяющиеся паттерны (>40% дублей)
5. Зацикливание точек/цифр (10+ подряд)
6. Уникальность слов (<15% уникальных = спам)
7. Преобладание спецсимволов

**Применяется на этапах**: 6, 7, 8, 9, 10, 13

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

**Версия**: 2.3.0 | **Статус**: ✅ Production Ready
