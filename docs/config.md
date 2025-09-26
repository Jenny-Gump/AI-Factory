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
WORDPRESS_USERNAME=PetrovA
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

##  Модели LLM

### Основные модели (DeepSeek FREE + Perplexity):
```python
LLM_MODELS = {
    "extract_prompts": "deepseek/deepseek-chat-v3.1:free",
    "create_structure": "deepseek/deepseek-chat-v3.1:free",
    "generate_article": "deepseek/deepseek-chat-v3.1:free",
    "fact_check": "perplexity/sonar-reasoning-pro:online",      # Обязательно :online для веб-поиска
    "editorial_review": "deepseek/deepseek-chat-v3.1:free",
    "link_planning": "deepseek/deepseek-chat-v3.1:free",
    "link_selection": "deepseek/deepseek-chat-v3.1:free",
}
```

### Fallback модели (Gemini 2.5 Flash Lite):
```python
FALLBACK_MODELS = {
    "extract_prompts": "google/gemini-2.5-flash-lite-preview-06-17",
    "create_structure": "google/gemini-2.5-flash-lite-preview-06-17",
    "generate_article": "google/gemini-2.5-flash-lite-preview-06-17",
    "fact_check": "google/gemini-2.5-flash-lite-preview-06-17",         # Fallback для fact-check
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

### Провайдеры LLM:
```python
LLM_PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models": ["deepseek-reasoner", "deepseek-chat"]
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "models": [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-2.5-flash-lite-preview-06-17",
            "deepseek/deepseek-chat-v3.1:free"
        ]
    }
}
```

## Batch Processing настройки (batch_config.py)

### Основные параметры BATCH_CONFIG:
```python
BATCH_CONFIG = {
    # Лимиты ресурсов
    "max_memory_mb": 2048,                    # Лимит памяти в MB
    "max_concurrent_requests": 5,             # Параллельные HTTP запросы

    # Retry политика
    "retry_failed_topics": 2,                 # Количество повторов для неудачных тем
    "retry_delay_seconds": 60,                # Задержка между повторами (сек)

    # Безопасность и надежность
    "autosave_interval": 300,                 # Автосохранение каждые 5 минут
    "enable_memory_monitoring": True,         # Мониторинг памяти
    "verify_publication_before_next": True,   # Проверка публикации перед следующей темой

    # Логирование
    "detailed_progress_logging": True,        # Детальное логирование прогресса
    "save_failed_topics_log": True           # Сохранять лог неудачных тем
}
```

### Типы контента CONTENT_TYPES:
```python
CONTENT_TYPES = {
    "basic_articles": {
        "prompts_folder": "prompts/basic_articles",
        "description": "Basic informational articles with FAQ and sources",
        "default_topics_file": "topics_basic_articles.txt",
        "output_prefix": "article_",
        "wordpress_category": "articles"
    },
    "guides": {
        "prompts_folder": "prompts/guides",
        "description": "Comprehensive step-by-step guides and tutorials",
        "default_topics_file": "topics_guides.txt",
        "output_prefix": "guide_",
        "wordpress_category": "guides"
    }
}
```

### Очистка памяти MEMORY_CLEANUP:
```python
MEMORY_CLEANUP = {
    "force_gc_between_topics": True,      # Принудительный garbage collection
    "clear_llm_caches": True,             # Очистка кэшей LLM клиентов
    "reset_token_tracker": True,          # Сброс token tracker между темами
    "close_http_connections": True,       # Закрытие HTTP соединений
    "clear_firecrawl_cache": True,        # Очистка кэша Firecrawl
}
```

### Пути файлов BATCH_PATHS:
```python
BATCH_PATHS = {
    "progress_file_template": ".batch_progress_{content_type}.json",
    "failed_topics_log": "batch_failed_topics.log",
    "batch_statistics": "batch_stats.json",
    "lock_file_template": ".batch_lock_{content_type}.pid"
}
```

##  Batch Processor (batch_processor.py)

### Основные возможности:
- **Последовательная обработка** тем из файла (одна за другой)
- **Автоматическое возобновление** прерванных сессий с флагом `--resume`
- **Мониторинг памяти** с автоматической очисткой между темами
- **Retry логика** для неудачных тем (до 3 попыток)
- **Блокировка процессов** - предотвращает запуск нескольких instance одновременно
- **Поддержка разных типов контента** через флаг `--content-type`

### Базовое использование:
```bash
# Обработка базовых статей (по умолчанию)
python3 batch_processor.py topics_basic_articles.txt

# Обработка с указанием типа контента
python3 batch_processor.py topics_guides.txt --content-type guides

# Без публикации в WordPress
python3 batch_processor.py topics.txt --skip-publication

# Возобновление прерванной сессии
python3 batch_processor.py topics.txt --resume
```

### Кастомные модели:
```bash
# С кастомной моделью для генерации
python3 batch_processor.py topics.txt --generate-model "deepseek-reasoner"

# С кастомными моделями для разных этапов
python3 batch_processor.py topics.txt \
    --extract-model "openai/gpt-4o" \
    --generate-model "deepseek-reasoner" \
    --editorial-model "google/gemini-2.5-flash-lite-preview-06-17"

# Комбинирование всех опций
python3 batch_processor.py topics_guides.txt \
    --content-type guides \
    --generate-model "deepseek-reasoner" \
    --skip-publication \
    --resume
```

### Формат файла тем:
```text
# topics_basic_articles.txt
API автоматизация в 2024 году
Машинное обучение для начинающих
Кибербезопасность в облачных технологиях
# Комментарии начинающиеся с # игнорируются
Разработка мобильных приложений 2025 тренды
```

### Функции безопасности:
- **Lock файлы**: `.batch_lock_{content_type}.pid` предотвращают двойной запуск
- **Progress файлы**: `.batch_progress_{content_type}.json` для возобновления
- **Memory monitoring**: Автоматические предупреждения при превышении лимитов
- **Graceful shutdown**: Корректная обработка Ctrl+C с сохранением прогресса

##  Запуск с кастомными настройками

### Традиционные флаги main.py:
```bash
# main.py НЕ поддерживает флаги моделей - используйте batch_processor.py
python3 main.py "API автоматизация в 2024"  # Всегда basic_articles по умолчанию
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