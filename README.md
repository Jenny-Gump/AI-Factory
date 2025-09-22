# Content Factory

Автоматизированный пайплайн для генерации высококачественного контента с публикацией в WordPress. Специализируется на создании **информационных статей с FAQ** и источниками.

## Основные возможности

- **Специализация**: Информационные статьи (`basic_articles`) - 11-этапный пайплайн с FAQ и источниками
- **Multi-LLM система**: 100% бесплатный DeepSeek по умолчанию + автоматические ретраи + фоллбек на Gemini 2.5
- **WordPress интеграция**: Автоматическая публикация на https://ailynx.ru с Yoast SEO
- **Система надежности**: 3 ретрая + фоллбек модели при сбоях
- **Token tracking**: Детальная аналитика использования с информацией о моделях
- **Русский язык**: Специализация на российскую аудиторию

---

## Быстрый старт

### 1. Установка
```bash
pip install -r requirements.txt
```

### 2. API ключи в .env файле
```bash
FIRECRAWL_API_KEY=your_key
OPENROUTER_API_KEY=your_key  # ОБЯЗАТЕЛЬНО (для fallback моделей - Gemini 2.5 + БЕСПЛАТНЫЙ DeepSeek)
DEEPSEEK_API_KEY=your_key    # Опционально (для прямого доступа к DeepSeek)
```

### 3. Запуск

#### Основное использование
```bash
# Генерация статьи с автоматической публикацией в WordPress
python3 main.py "промпты для маркетинга"

# main.py использует пайплайн basic_articles (информационные статьи с FAQ)
python3 main.py "промпты для бизнеса"
```

#### Информационные статьи с FAQ
```bash
# Информационные статьи с FAQ и источниками (по умолчанию)
python3 main.py "API автоматизация в 2024"

# Все статьи публикуются в WordPress автоматически
python3 main.py "Машинное обучение тренды 2024"
```

#### Расширенные опции
```bash
# main.py не поддерживает флаги моделей - используйте batch_processor.py
# Для кастомных моделей используйте пакетную обработку:
python3 batch_processor.py your_topics.txt --generate-model "deepseek-reasoner" --skip-publication
```

---

## Как это работает

### Пайплайн "Информационные статьи" (basic_articles)

**Этапы 1-6 (общие):**
1. **Поиск** - Находит 20 релевантных URL по теме
2. **Парсинг** - Извлекает контент с найденных сайтов
3. **Оценка** - Ранжирует источники по качеству
4. **Отбор** - Выбирает топ-5 лучших источников
5. **Очистка** - Убирает "мусор" из контента

**Этапы 7-11 (специфичные):**
7. **Извлечение структур** - LLM анализирует структуру каждого источника отдельно
8. **Создание ультимативной структуры** - LLM объединяет 5 структур + добавляет FAQ и Источники
9. **Генерация статьи** - LLM пишет статью с FAQ блоками и нумерованными ссылками [1]-[5]
10. **Редакторский обзор** - Специальная обработка FAQ форматирования
11. **Публикация** - Автоматически публикует в WordPress (опционально)

### Основные отличия:

| Особенность | prompt_collection | basic_articles |
|-------------|-------------------|----------------|
| **Тип контента** | Коллекции промптов | Информационные статьи |
| **FAQ раздел** | Нет | Да (`<details><summary>`) |
| **Источники** | Нет | Да (нумерованные [1]-[5]) |
| **Этапов** | 8 | 11 |
| **Время выполнения** | ~6-8 мин | ~8-10 мин |

### Link Processing (Обработка ссылок)

**NEW:** Автоматическое добавление 10-20 авторитетных внешних ссылок в статьи:

- **Умное позиционирование**: Автоматическая коррекция позиций для естественного размещения маркеров
- **Академический приоритет**: docs.* → arxiv.org → github.com → остальные источники
- **Защита от ошибок**: Компактный JSON (только позиции, без HTML) = стабильность
- **Высокая успешность**: 90-95% запланированных ссылок находятся и вставляются

**Процесс:**
1. LLM анализирует контент и определяет позиции для 10-20 ссылок
2. Firecrawl API ищет кандидатов по сгенерированным запросам
3. Система выбирает лучшие источники (блокирует reddit, medium, stackoverflow)
4. Маркеры [1], [2], [3] вставляются в текст с умной коррекцией позиций
5. Создается раздел "Полезные ссылки" в конце статьи

### Мониторинг процесса

Pipeline включает детальный мониторинг и систему надежности:
- **Ожидаемо**: Структурированные данные из 5 источников для создания статьи
- **Автоматические ретраи**: 3 попытки с задержками 2с → 5с → 10с
- **Фоллбек модели**: Автоматическое переключение при сбоях
- **Отчетность**: Статистика успешности и использования моделей
- **Предупреждения**: Уведомления о проблемных источниках и моделях
- **Логи**: Детальная информация о каждой попытке запроса

## Пакетная обработка

Для массовой генерации контента используйте batch режим:

#### Базовая пакетная обработка
```bash
# Базовая пакетная обработка (автоматически использует basic_articles)
python3 batch_processor.py topics_basic_articles.txt

# Без публикации в WordPress
python3 batch_processor.py topics_basic_articles.txt --skip-publication

# С возобновлением
python3 batch_processor.py topics_basic_articles.txt --resume
```

#### Расширенные опции пакетной обработки
```bash
# С кастомными моделями
python3 batch_processor.py topics_basic_articles.txt --extract-model "deepseek-reasoner"

# С публикацией в WordPress
python3 batch_processor.py topics_basic_articles.txt

# С возобновлением прерванной обработки
python3 batch_processor.py topics_basic_articles.txt --resume

# С премиум моделями
python3 batch_processor.py topics_basic_articles.txt --generate-model deepseek-reasoner --skip-publication
```

**Формат файла тем**: одна тема на строку
```
# Файл: topics_basic_articles.txt
API автоматизация в 2024 году
Машинное обучение для начинающих
Кибербезопасность в облачных технологиях
Разработка мобильных приложений 2025 тренды
```

## Тестирование WordPress

```bash
# Создание категории (одноразово)
python3 create_prompts_category.py

# Тест публикации
python3 test_publication_auto.py
```

## Результат работы

Все артефакты сохраняются в `output/Your_Topic/`:
- Найденные промпты (`all_prompts.json`)
- Готовая статья (`wordpress_data.json`) 
- Отчет по токенам (`token_usage_report.json`)
- Результат публикации (`wordpress_publication_result.json`)

**WordPress публикация:**
- Сайт: https://ailynx.ru
- Категория: "prompts" (ID: 825)
- Статус: draft (для проверки)
- Yoast SEO: Custom Post Meta Endpoint для записи мета-полей
- Автоматическое заполнение всех SEO полей

## Оптимизация памяти и производительности

### Очистка памяти между темами

Batch processor автоматически очищает память между обработкой тем:

**Реализованные оптимизации:**
- **Принудительная сборка мусора** (`gc.collect()`) после каждой темы
- **Очистка кэшей LLM клиентов** - удаление накопленных OpenAI клиентов
- **Очистка HTTP соединений** - принудительная очистка aiohttp соединений
- **Автоматический сброс TokenTracker** - создается заново для каждой темы
- **Мониторинг памяти** - проверка каждые 5 минут с предупреждениями

**Настройки памяти** (`batch_config.py`):
```python
MEMORY_CLEANUP = {
    "force_gc_between_topics": True,     # Принудительный garbage collection
    "clear_llm_caches": True,           # Очистка кэшей LLM клиентов
    "reset_token_tracker": True,        # Сброс token tracker
    "close_http_connections": True,     # Закрытие HTTP соединений
    "clear_firecrawl_cache": True,      # Очистка кэша Firecrawl
}

# Лимит памяти: 2048MB (2GB)
"max_memory_mb": 2048
```

**Логи очистки:**
```
Cleaning up memory between topics...
Garbage collection: 847 objects collected
LLM clients cache cleared
Forcing cleanup of HTTP connections...
HTTP connections cleanup: 23 objects collected
TokenTracker is automatically reset per topic
Memory after cleanup: 156.3MB
```

**Синхронная архитектура:** Убрана вся асинхронность из всей системы включая link processing - простой последовательный пайплайн без deadlock'ов.

### Section Generation (Генерация секций)

**NEW:** Полностью переписанная система генерации секций без асинхронности:

- **Sequential Processing**: Секции генерируются последовательно, одна за другой
- **No Async Deadlocks**: Убраны все `asyncio`, `nest_asyncio` и таймауты
- **Clear Progress**: Простые логи "1/3 sections", "2/3 sections", etc.
- **Reliable Retries**: 3 попытки на секцию с прогрессивной задержкой
- **Detailed Reporting**: Финальный отчет с success rate и статистикой

**Процесс:**
1. Парсинг структуры секций из ultimate_structure
2. Последовательная генерация каждой секции (for loop)
3. Синхронные LLM запросы с retry логикой
4. Сохранение промежуточных результатов
5. Объединение всех секций в финальную статью

**Логи системы:**
```
Generating section 1/3: Введение
Successfully generated section 1/3: Введение
Generating section 2/3: Основы
Successfully generated section 2/3: Основы
SECTION GENERATION REPORT:
Completed: 3/3 sections
Success rate: 100.0%
Article generation complete
```

## 📋 Changelog

### 🔍 September 20, 2025 - Improved Link Anchor Selection

- **🎯 Better Anchor Selection**: LLM теперь избегает выбора якорей внутри HTML тегов (h2, h3, code, strong, em)
- **📝 HTML Preprocessing**: Добавлены маркеры [HEADER_START], [CODE_START], [FORMAT_START] для обозначения зон
- **✅ Simplified Validation**: Упрощена проверка - только anchor_text без строгого контекста
- **🔄 Fallback Search**: При неудаче поиска в HTML используется BeautifulSoup для нормализованного текста
- **📚 Documentation Update**: Обновлена документация link_processing.md с новой логикой

### 🛠️ September 20, 2025 - Complete Sync Architecture

- **🔧 Link Processing Sync**: Убрана ВСЯ асинхронность из LinkProcessor - все функции синхронные
- **🚫 Event Loop Fix**: Исправлен конфликт "Cannot run event loop while another loop is running"
- **📝 Sequential Pipeline**: Весь пайплайн теперь последовательный без async/await
- **⚡ SyntaxError Fix**: Убран await из несинхронных функций в main.py
- **🔧 Architecture Alignment**: Документация обновлена в соответствии с реальным кодом

### 🎉 September 21, 2025 - DeepSeek FREE как основная модель

**Основные изменения:**
- **🆓 100% БЕСПЛАТНЫЕ модели**: DeepSeek FREE теперь основная модель для всех этапов
- **🚀 Модель по умолчанию**: `deepseek/deepseek-chat-v3.1:free` для всех этапов
- **📈 Fallback система**: Автоматическое переключение на Gemini 2.5 при сбоях DeepSeek
- **⚡ Система флагов**: Полный контроль через `--extract-model`, `--generate-model` и `--editorial-model`

**Обновления API:**
- **OPENROUTER_API_KEY** обязательный (для fallback Gemini 2.5 + доступа к DeepSeek FREE)
- **DEEPSEEK_API_KEY** опционален (для прямого доступа к DeepSeek)

**Доступные модели:**
- `deepseek/deepseek-chat-v3.1:free` - **По умолчанию (БЕСПЛАТНО)**
- `x-ai/grok-4-fast:free` - **Для редактуры (БЕСПЛАТНО)**
- `google/gemini-2.5-flash-lite-preview-06-17` (65K) - Fallback модель
- `deepseek-reasoner`, `openai/gpt-4o`, `openai/gpt-4o-mini` - Альтернативы

## 📚 Документация

- **[docs/INDEX.md](docs/INDEX.md)** - 📖 Навигатор по всей документации
- **[docs/flow.md](docs/flow.md)** - Детальное описание каждого этапа пайплайна
- **[docs/config.md](docs/config.md)** - Конфигурация и настройка API ключей
- **[docs/troubleshooting.md](docs/troubleshooting.md)** - Решение проблем и отладка
- **[docs/WORDPRESS_INTEGRATION.md](docs/WORDPRESS_INTEGRATION.md)** - WordPress интеграция

## 🔧 Отладка

При ошибках JSON парсинга (например, "Expecting value: line 5241") все сырые ответы LLM автоматически сохраняются в папки `output/{topic}/*/llm_responses_raw/` для анализа. Подробности в [docs/flow.md](docs/flow.md#система-сохранения-сырых-ответов-llm).

---

**Время выполнения**: ~6-10 минут | **Токенов**: ~35k | **Статус**: ✅ Готов к использованию