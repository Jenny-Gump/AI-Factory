#  Configuration Guide

Полное руководство по настройке Content Factory для вашего окружения.

##  Основная конфигурация

Все настройки хранятся в `src/config.py` и `.env` файле.

##  API Ключи (.env файл)

### Обязательные ключи:
```bash
# Firecrawl - для поиска и парсинга контента
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# OpenRouter - для доступа к LLM моделям (DeepSeek FREE + Gemini fallback)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
```

### Опциональные ключи:
```bash
# DeepSeek - прямой доступ к DeepSeek API (не обязательно)
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# WordPress - для автоматической публикации
WORDPRESS_URL=https://ailynx.ru
WORDPRESS_USERNAME=admin
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

##  Модели LLM

### Основные модели (DeepSeek FREE):
```python
LLM_MODELS = {
    "extract_prompts": "deepseek/deepseek-chat-v3.1:free",
    "create_structure": "deepseek/deepseek-chat-v3.1:free",
    "generate_article": "deepseek/deepseek-chat-v3.1:free",
    "editorial_review": "deepseek/deepseek-chat-v3.1:free",
    "link_planning": "deepseek/deepseek-chat-v3.1:free",
    "link_selection": "deepseek/deepseek-chat-v3.1:free",
}
```

### Fallback модели (Gemini 2.5):
```python
FALLBACK_MODELS = {
    "extract_prompts": "google/gemini-2.5-flash-lite-preview-06-17",
    "create_structure": "google/gemini-2.5-flash-lite-preview-06-17",
    "generate_article": "google/gemini-2.5-flash-lite-preview-06-17",
    "editorial_review": "google/gemini-2.5-flash-lite-preview-06-17",
    "link_planning": "google/gemini-2.5-flash-lite-preview-06-17",
    "link_selection": "google/gemini-2.5-flash-lite-preview-06-17",
}
```

##  Параметры производительности

### Параллельность и лимиты:
```python
# Количество параллельных запросов к Firecrawl
CONCURRENT_REQUESTS = 5

# Минимальная длина контента (символы)
MIN_CONTENT_LENGTH = 10000

# Количество источников для обработки
TOP_N_SOURCES = 5
```

### Таймауты:
```python
# Таймаут для генерации секции (секунды)
SECTION_TIMEOUT = 180  # 3 минуты

# Таймаут для каждой модели
MODEL_TIMEOUT = 60  # 1 минута

# Максимум попыток на секцию
SECTION_MAX_RETRIES = 3
```

##  Веса для оценки источников

```python
# Веса для формулы: Final = (trust * 0.5) + (relevance * 0.3) + (depth * 0.2)
TRUST_SCORE_WEIGHT = 0.5      # Доверие к домену
RELEVANCE_SCORE_WEIGHT = 0.3  # Релевантность теме
DEPTH_SCORE_WEIGHT = 0.2      # Глубина контента
```

##  Настройки Link Processing

```python
# Включить/выключить обработку ссылок
LINK_PROCESSING_ENABLED = True

# Максимум ссылок для вставки
LINK_MAX_QUERIES = 15

# Кандидатов на запрос
LINK_MAX_CANDIDATES_PER_QUERY = 5

# Таймауты для поиска ссылок (секунды)
LINK_PROCESSING_TIMEOUT = 360  # 6 минут общий
LINK_SEARCH_TIMEOUT = 6        # На один поиск
```

##  WordPress настройки

```python
# API endpoint
WORDPRESS_API_URL = "https://ailynx.ru/wp-json/wp/v2"

# Категория для публикации
WORDPRESS_CATEGORY = "prompts"  # ID: 825

# Статус публикации
WORDPRESS_STATUS = "draft"  # Черновик для проверки

# Custom Post Meta endpoint для SEO
USE_CUSTOM_META_ENDPOINT = True
```

##  Дополнительные настройки

### Фильтры доменов:
- `filters/blocked_domains.json` - заблокированные домены
- `filters/trusted_sources.json` - доверенные источники
- `filters/preferred_domains.json` - приоритетные для ссылок

### Retry логика:
```python
RETRY_CONFIG = {
    "max_attempts": 3,
    "delays": [2, 5, 10],  # Задержки между попытками
    "use_fallback_on_final_failure": True
}
```

##  Запуск с кастомными настройками

### Batch processing с флагами:
```bash
# С кастомной моделью для генерации
python3 batch_processor.py topics.txt --generate-model "deepseek-reasoner"

# Без публикации в WordPress
python3 batch_processor.py topics.txt --skip-publication

# С кастомными моделями для разных этапов
python3 batch_processor.py topics.txt \
    --extract-model "openai/gpt-4o" \
    --generate-model "deepseek-reasoner" \
    --editorial-model "google/gemini-2.5-flash-lite-preview-06-17"
```

##  Проверка конфигурации

```bash
# Проверить наличие всех ключей
python3 -c "from src.config import *; print('Config OK')"

# Тест соединения с WordPress
python3 test_publication_auto.py

# Проверить Firecrawl API
curl -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
     https://api.firecrawl.dev/v2/search
```

##  Оптимизация для скорости

Для ускорения:
1. Увеличьте `CONCURRENT_REQUESTS` до 8-10
2. Уменьшите `TOP_N_SOURCES` до 3-4
3. Уменьшите `MIN_CONTENT_LENGTH` до 5000
4. Отключите `LINK_PROCESSING_ENABLED`

##  Оптимизация для качества

Для улучшения качества:
1. Увеличьте `TOP_N_SOURCES` до 7-10
2. Увеличьте `MIN_CONTENT_LENGTH` до 15000
3. Используйте премиум модели вместо FREE
4. Увеличьте `LINK_MAX_QUERIES` до 20