#  Configuration Guide

Полное руководство по настройке Content Factory для вашего окружения.

##  Основная конфигурация

Все настройки хранятся в `src/config.py` и `.env` файле.

##  API Ключи (.env файл)

### Обязательные ключи:
```bash
# Firecrawl - для поиска и парсинга контента
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# OpenRouter - для доступа к LLM моделям (DeepSeek FREE)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx

# Google Gemini - ОБЯЗАТЕЛЬНО для факт-чекинга с веб-поиском
GEMINI_API_KEY=AIzaSyAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
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

### Основные модели (DeepSeek FREE + Google Gemini):
```python
LLM_MODELS = {
    "extract_sections": "deepseek-reasoner",                             # DeepSeek Reasoner для извлечения промптов
    "create_structure": "deepseek-reasoner",                            # DeepSeek Reasoner для создания структуры
    "generate_article": "deepseek-reasoner",                            # DeepSeek Reasoner для генерации статей
    "fact_check": "gemini-2.5-flash-preview-09-2025",                   # Google Gemini с нативным веб-поиском
    "link_placement": "gemini-2.5-flash-preview-09-2025",               # Google Gemini с нативным веб-поиском для поиска ссылок
    "translation": "deepseek-reasoner",                                 # DeepSeek Reasoner для перевода
    "editorial_review": "deepseek-reasoner",                            # DeepSeek Reasoner для редакторской правки
}
```

### Fallback модели:
```python
FALLBACK_MODELS = {
    "extract_sections": "google/gemini-2.5-flash-lite-preview-06-17",
    "create_structure": "google/gemini-2.5-flash-lite-preview-06-17",
    "generate_article": "google/gemini-2.5-flash-lite-preview-06-17",
    "fact_check": "gemini-2.5-flash",                                   # Stable Gemini 2.5 Flash with web search
    "link_placement": "gemini-2.5-flash",                               # Stable Gemini 2.5 Flash with web search
    "translation": "google/gemini-2.5-flash-lite-preview-06-17",        # Fallback для перевода
    "editorial_review": "google/gemini-2.5-flash-lite-preview-06-17",   # Fallback для редакторской правки
}
```

### Provider Preferences для DeepSeek (OpenRouter):

**ВАЖНО**: Эта настройка применяется ТОЛЬКО для DeepSeek FREE моделей через OpenRouter.

```python
# В src/config.py (строки 130-133)
"provider_preferences": {
    "order": ["DeepInfra"],      # Приоритет роутинга на DeepInfra
    "allow_fallbacks": False     # Запретить fallback на другие провайдеры
}
```

**Как работает:**
- Применяется автоматически для всех DeepSeek моделей (проверка в `src/llm_processing.py:824-831`)
- Гарантирует routing запросов через DeepInfra провайдер
- Предотвращает fallback на альтернативные провайдеры OpenRouter
- Для других моделей (Gemini, GPT) эта настройка НЕ применяется

**Логика применения:**
```python
# src/llm_processing.py (строки 822-831)
if provider == "openrouter":
    # Apply provider preferences ONLY for DeepSeek models
    if "deepseek" in model_name.lower():
        provider_config = LLM_PROVIDERS.get(provider, {})
        provider_prefs = provider_config.get("provider_preferences")
        if provider_prefs:
            kwargs["extra_body"] = {"provider": provider_prefs}
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

### Retry логика (ОБНОВЛЕНО - Sep 27, 2025):
```python
RETRY_CONFIG = {
    "max_attempts": 3,
    "delays": [2, 5, 10],  # Задержки между попытками
    "use_fallback_on_final_failure": True
}
```

### 🆕 Продвинутая Editorial Review система:
Начиная с версии от 27 сентября 2025, этап Editorial Review имеет собственную продвинутую retry систему:

- **3 попытки с primary моделью** (DeepSeek Chat v3.1)
- **4 уровня JSON нормализации** для каждой попытки
- **Автоматический fallback на Gemini 2.5** при неудаче primary модели
- **3 попытки с fallback моделью** с теми же 4 уровнями нормализации
- **Детальное логирование** каждого этапа для диагностики

**Архитектура retry:**
```
Editorial Review → Primary Model (DeepSeek)
├── Attempt 1 → JSON Parse (4 levels)
├── Attempt 2 → JSON Parse (4 levels)
├── Attempt 3 → JSON Parse (4 levels)
└── Fallback Model (Gemini 2.5)
    ├── Attempt 1 → JSON Parse (4 levels)
    ├── Attempt 2 → JSON Parse (4 levels)
    └── Attempt 3 → JSON Parse (4 levels)
```

**Уровни JSON нормализации:**
1. **Direct parsing** - стандартная очистка markdown блоков
2. **Escaping fixes** - исправление проблем с экранированием
3. **Block extraction** - извлечение JSON через regex
4. **Incomplete repair** - восстановление незакрытых скобок

### 🔧 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Newlines в code блоках (Sept 27, 2025):
Исправлена критическая проблема с отображением code блоков в HTML выводе:

**Проблема:**
- LLM модели экранируют переносы строк как `\\n` в JSON ответе (двойной backslash + n)
- Функция `save_artifact()` сохраняла эти символы как literal `\n` в HTML
- Код становился нечитаемым: `from transformers import AutoModel\nimport torch\nmodel = AutoModel.from_pretrained("model-name")`
- Пользователь не мог скопировать рабочий код из статей

**Техническая причина:**
- Промпт editorial review требует экранирования: `"Escape all newlines as \\n in JSON"`
- JSON parser преобразует `\\n` в literal string `\n` (backslash + n как два символа)
- `save_artifact()` записывает эти символы как есть, без преобразования в реальные переносы

**Решение:**
Добавлена системная функция `fix_content_newlines()` в `main.py`:
- Использует общий подход для исправления во всех типах контента (HTML и JSON)
- Заменяет `\\n` на настоящие переносы строк ТОЛЬКО внутри code блоков и code spans
- Безопасно: не затрагивает остальной контент
- Поддерживает множественные форматы: `<pre><code>`, `<code>`, markdown code blocks

**Техническая реализация:**
```python
def fix_content_newlines(content):
    """Исправляет переносы строк в code блоках"""
    # Исправляем в <pre><code> блоках
    content = re.sub(
        r'(<pre[^>]*><code[^>]*>)(.*?)(</code></pre>)',
        lambda m: m.group(1) + m.group(2).replace('\\n', '\n') + m.group(3),
        content, flags=re.DOTALL
    )

    # Исправляем в inline <code> блоках
    content = re.sub(
        r'(<code[^>]*>)(.*?)(</code>)',
        lambda m: m.group(1) + m.group(2).replace('\\n', '\n') + m.group(3),
        content, flags=re.DOTALL
    )

    return content
```

**Результат:**
```python
# ❌ ДО исправления (одна строка):
from transformers import AutoModel\nimport torch\nmodel = AutoModel.from_pretrained("model-name")

# ✅ ПОСЛЕ исправления (правильные переносы):
from transformers import AutoModel
import torch
model = AutoModel.from_pretrained("model-name")
```

**Применение:**
- Применяется автоматически перед сохранением JSON и HTML файлов
- Исправление работает во всех этапах pipeline
- Существующие статьи можно исправить через `--start-from-stage editorial_review`

## 🆕 Google Gemini интеграция (Сентябрь 27, 2025)

### Критическое обновление факт-чекинга:
Заменили **Perplexity Sonar** на **Google Gemini 2.5 Flash** для факт-чекинга из-за серьезных проблем с качеством:

**Проблема с Perplexity:**
- ❌ Perplexity **искажал правильные команды**: `ollama pull mistral` → `ollama pull mistral:7b`
- ❌ Качество факт-чекинга: **6/10** (часто вносил ошибки вместо исправлений)
- ❌ Неэффективный веб-поиск через OpenRouter

**Решение - Google Gemini:**
- ✅ **Нативный веб-поиск** через Google Search API
- ✅ Качество факт-чекинга: **9.5/10** (точные исправления на основе актуальных данных)
- ✅ **10+ веб-запросов** за один факт-чек
- ✅ **Прямая интеграция** с Google API (не через OpenRouter)

### Техническая архитектура:
```python
# Прямой HTTP запрос к Google API с преобразованием формата
def _make_google_direct_request(model_name, messages, **kwargs):
    # OpenAI format → Google contents format
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    request_data = {
        "contents": [{"role": "user", "parts": [{"text": combined_content}]}],
        "tools": [{"google_search": {}}],  # Нативный веб-поиск
        "generationConfig": {"maxOutputTokens": 30000}
    }
```

### Требования для интеграции:
1. **API ключ Google Gemini** в `.env`:
   ```bash
   GEMINI_API_KEY=AIzaSyAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

2. **Модель факт-чекинга** в `config.py`:
   ```python
   LLM_MODELS = {
       "fact_check": "gemini-2.5-flash"  # Вместо perplexity/sonar
   }
   ```

3. **Провайдер google_direct** добавлен автоматически

### Результаты тестирования:
- ✅ **Фактические ошибки исправляются корректно** (2025→2020, 200B→175B параметров)
- ✅ **Авторитетные ссылки** добавляются автоматически (официальные docs, GitHub)
- ✅ **Веб-поиск работает** - модель находит актуальную информацию
- ✅ **Совместимость** с существующим кодом через wrapper

### Провайдеры LLM:
```python
LLM_PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models": ["deepseek-reasoner", "deepseek-chat"]
    },
    "google_direct": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key_env": "GEMINI_API_KEY",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash"
        ],
        "supports_web_search": True  # Нативный веб-поиск
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

##  Оптимизация для качества

Для улучшения качества:
1. Увеличьте `TOP_N_SOURCES` до 7-10
2. Увеличьте `MIN_CONTENT_LENGTH` до 15000
3. Используйте премиум модели вместо FREE

##  Запуск с конкретного этапа

Начиная с версии от 27 сентября 2025, добавлена возможность запуска pipeline с конкретного этапа для тестирования и отладки.

### Использование флага --start-from-stage:
```bash
# Доступные этапы:
# - fact_check: факт-чекинг секций через Google Gemini с нативным веб-поиском
# - editorial_review: редакторская правка и финальное форматирование
# - publication: публикация готовой статьи в WordPress
```

### Требования для каждого этапа:
- **Общее**: Должна существовать папка `output/{topic}/` с результатами предыдущих этапов
- **translation**: требуется `08_article_generation/wordpress_data.json` с `generated_sections`
- **fact_check**: требуется `09_translation/translated_sections.json`
- **link_placement**: требуется `10_fact_check/fact_checked_content.json`
- **editorial_review**: требуется `11_link_placement/content_with_links.json` (или `10_fact_check/fact_checked_content.json` если link_placement пропущен)
- **publication**: требуется `12_editorial_review/wordpress_data_final.json`

### Примеры использования:
```bash
# Запуск только перевода (после генерации секций)
python3 main.py "Test" --start-from-stage translation
# Требуется: 08_article_generation/wordpress_data.json
# Время: ~3-5 минут

# Запуск только факт-чека (после перевода)
python3 main.py "Test" --start-from-stage fact_check
# Требуется: 09_translation/translated_sections.json
# Время: ~3-5 минут

# Запуск только расстановки ссылок (после факт-чека)
python3 main.py "Test" --start-from-stage link_placement
# Требуется: 10_fact_check/fact_checked_content.json
# Время: ~2-3 минуты

# Запуск только редактуры (после расстановки ссылок)
python3 main.py "Test" --start-from-stage editorial_review
# Требуется: 11_link_placement/content_with_links.json
# Время: ~2-3 минуты

# Запуск только публикации (после редактуры)
python3 main.py "Test" --start-from-stage publication
# Требуется: 12_editorial_review/wordpress_data_final.json
# Время: ~10-20 секунд

# Отключить расстановку ссылок
python3 main.py "Test" --link-placement-mode off
# Link placement будет пропущен, контент пойдет напрямую из fact_check в editorial_review

# Полный пример для тестирования исправлений в редакторе
python3 main.py "Mistral local model installation guide" --start-from-stage editorial_review
```

### Польза:
- ⚡ Быстрое тестирование изменений в коде
- 🐛 Отладка конкретных этапов
- 💾 Экономия токенов при разработке
- 🔧 Тестирование исправлений без полного перезапуска

## 🔧 Система логирования

### Обычный режим (по умолчанию):
```bash
python main.py "тема"                # Только ключевые этапы
python batch_processor.py topics.txt # Тихий batch режим
```

### Verbose режим (детальный):
```bash
python main.py "тема" --verbose          # Все детали и отладка
python batch_processor.py topics.txt --verbose # Детальный batch
```

**Подробности**: См. [LOGGING.md](LOGGING.md) для полного описания режимов логирования, фильтрации сообщений и предупреждений о факт-чеке.