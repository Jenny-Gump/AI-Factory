# Content Factory

Автоматизированный 13-этапный пайплайн для генерации высококачественного контента с публикацией в WordPress.

## ✨ Основные возможности

- **100% бесплатные LLM**: DeepSeek Chat v3.1 FREE + Google Gemini 2.5 Flash (fact-check с веб-поиском)
- **13-этапный пайплайн**: 1-6: Сбор данных → 7: Ультимативная структура → 8: Генерация → 9: Translation → 10: Fact-check → 11: Link placement → 12: Editorial review → 13: WordPress (опционально)
- **💰 Cost Tracking**: Автоматический подсчет токенов и стоимости в USD для всех LLM запросов с детальными отчетами по стадиям и моделям
- **WordPress интеграция**: Автоматическая публикация с Yoast SEO
- **Система переменных**: Кастомизация стиля, аудитории, тона через CLI
- **Надежность**: Унифицированная retry/fallback система с 6 автоматическими попытками (3 primary + 3 fallback) и post-processor паттерном для защиты от JSON parsing ошибок

---

## 🚀 Быстрый старт

### 1. Установка
```bash
pip install -r requirements.txt
```

### 2. API ключи (.env файл)
```bash
FIRECRAWL_API_KEY=your_key
OPENROUTER_API_KEY=your_key  # Обязательно
GEMINI_API_KEY=your_key       # Обязательно для fact-check
```

### 3. Запуск
```bash
# Базовая генерация
python3 main.py "тема статьи"

# С кастомизацией
python3 main.py "ИИ в бизнесе" \
  --author-style "technical" \
  --target-audience "разработчики" \
  --article-length 8000

# Пакетная обработка
python3 batch_processor.py topics.txt
```

---

## 📚 Документация

### Центральный индекс:
- **[docs/INDEX.md](docs/INDEX.md)** - Навигация по всей документации проекта

### Для начинающих:
- **[docs/GUIDE.md](docs/GUIDE.md)** - Полное руководство пользователя
- **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - FAQ и решение проблем

### Для опытных:
- **[docs/TECHNICAL.md](docs/TECHNICAL.md)** - Техническая документация, API, архитектура
- **[docs/flow.md](docs/flow.md)** - Детальное описание всех 12 этапов пайплайна
- **[docs/LLM_RESPONSE_FORMATS.md](docs/LLM_RESPONSE_FORMATS.md)** - Форматы ответов LLM и JSON парсинг
- **[CHANGELOG.md](CHANGELOG.md)** - История изменений и версий

### Справочная информация:
- **[docs/config.md](docs/config.md)** - Полный справочник по конфигурации
- **[docs/COST_TRACKING.md](docs/COST_TRACKING.md)** - 💰 Система отслеживания токенов и стоимости
- **[docs/variables_quick_reference.md](docs/variables_quick_reference.md)** - Краткий справочник переменных
- **[docs/variables_system.md](docs/variables_system.md)** - Полная документация системы переменных
- **[docs/CONTENT_VALIDATION.md](docs/CONTENT_VALIDATION.md)** - Система валидации v3.0 (6 уровней научной защиты от спама)
- **[docs/LOGGING.md](docs/LOGGING.md)** - Система логирования и мониторинга

---

## 🎯 Основные команды

```bash
# Генерация статьи
python3 main.py "тема"

# С переменными
python3 main.py "тема" --author-style "technical" --language "english"

# Пакетная обработка
python3 batch_processor.py topics.txt

# Запуск с этапа
python3 main.py "тема" --start-from-stage fact_check

# Verbose режим
python3 main.py "тема" --verbose
```

---

## 📊 Результаты

Все артефакты сохраняются в `output/{topic}/`:
- Структура статьи (ultimate_structure)
- Готовая статья (wordpress_data.json)
- Отчет по токенам (token_usage_report.json)
- Результат публикации (wordpress_publication_result.json)

**Время выполнения**: ~12-17 минут | **Токены**: ~45-55k | **Статус**: ✅ Production Ready

---

## 🔧 Типы контента

### basic_articles (по умолчанию)
Информационные статьи с FAQ блоками, источниками [1]-[5] и внешними ссылками.

```bash
python3 main.py "API автоматизация" --content-type basic_articles
```

### guides
Пошаговые руководства и туториалы.

```bash
python3 main.py "Установка DeepSeek локально" --content-type guides
```

### reviews
Объективные обзоры продуктов и сервисов с практическим анализом.

```bash
python3 main.py "DeepSeek API review" --content-type reviews
```

---

## 📝 Версия

**Текущая версия**: 2.4.0 (October 9, 2025)

**Последние изменения**:
- ✅ **Unified Retry/Fallback System v2.4.0:** Post-processor паттерн для автоматического retry/fallback при JSON parsing ошибках
- ✅ **Архитектурное улучшение:** Унифицированные 6 попыток (3 primary + 3 fallback) на ВСЕХ этапах включая downstream обработку
- ✅ **Удалены outer retry loops:** 3 функции рефакторены для единообразной архитектуры (~50 строк кода удалено)
- ✅ **SOLID compliance:** Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion
- ✅ Translation stage (этап 9) - посекционный перевод на целевой язык
- ✅ Fact-check (этап 10) - проверка фактов на переведенном тексте + v3.0 validation (6 научных уровней)

Полная история: [CHANGELOG.md](CHANGELOG.md)

---

## 💬 Поддержка

- **Документация**: [docs/GUIDE.md](docs/GUIDE.md)
- **FAQ**: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- **Технические детали**: [docs/TECHNICAL.md](docs/TECHNICAL.md)

---

**License**: MIT | **Status**: ✅ Production Ready
