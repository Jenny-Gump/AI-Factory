# Content Factory

Автоматизированный 12-этапный пайплайн для генерации высококачественного контента с публикацией в WordPress.

## ✨ Основные возможности

- **100% бесплатные LLM**: DeepSeek Chat v3.1 FREE + Google Gemini 2.5 Flash (fact-check с веб-поиском)
- **12-этапный пайплайн**: Поиск → Парсинг → Генерация → Translation → Fact-check → Link placement → Публикация
- **WordPress интеграция**: Автоматическая публикация с Yoast SEO
- **Система переменных**: Кастомизация стиля, аудитории, тона через CLI
- **Надежность**: 3 ретрая + автоматический fallback между моделями

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

---

## 📝 Версия

**Текущая версия**: 2.3.0 (October 2025)

**Последние изменения**:
- ✅ Translation stage (этап 9) - посекционный перевод на целевой язык
- ✅ Fact-check (этап 10) - проверка фактов на переведенном тексте
- ✅ Link placement (этап 11) - расстановка ссылок на целевом языке
- ✅ v3.0 Multi-level validation - 6 научных уровней защиты от спама (compression ratio, Shannon entropy, character bigrams, word density, finish_reason, language check)

Полная история: [CHANGELOG.md](CHANGELOG.md)

---

## 💬 Поддержка

- **Документация**: [docs/GUIDE.md](docs/GUIDE.md)
- **FAQ**: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- **Технические детали**: [docs/TECHNICAL.md](docs/TECHNICAL.md)

---

**License**: MIT | **Status**: ✅ Production Ready
