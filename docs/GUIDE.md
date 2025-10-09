# Content Factory - Руководство пользователя

Полное руководство по использованию Content Factory для генерации высококачественного контента.

---

## 📋 Содержание

1. [Быстрый старт](#быстрый-старт)
2. [Как работает пайплайн](#как-работает-пайплайн)
3. [Переменные и кастомизация](#переменные-и-кастомизация)
4. [Режимы работы](#режимы-работы)
5. [Логирование и мониторинг](#логирование-и-мониторинг)

---

## 🚀 Быстрый старт

### Установка за 3 минуты

#### 1. Установка зависимостей
```bash
cd "Desktop/AI DEV/Content-factory"
pip install -r requirements.txt
```

#### 2. Настройка API ключей

Создайте файл `.env` в корне проекта:

```bash
# Обязательные ключи
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Опциональные (для WordPress публикации)
WORDPRESS_URL=https://your-site.com
WORDPRESS_USERNAME=your_username
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

#### 3. Первый запуск

```bash
# Простая генерация
python3 main.py "AI trends in 2025"

# С кастомизацией
python3 main.py "Машинное обучение" \
  --author-style "technical" \
  --target-audience "разработчики" \
  --language "русский"
```

**Результат**: Через 12-17 минут готовая статья в `output/{topic}/wordpress_data.json`

---

## 🔄 Как работает пайплайн

Content Factory - это 12-этапный автоматизированный конвейер для создания качественного контента.

### Обзор этапов

```
1-5:  Сбор данных       → Поиск + Парсинг + Оценка + Отбор + Очистка
6-8:  Структурирование  → Извлечение структур → Ultimate structure → Генерация
9-12: Обогащение        → Translation → Fact-check → Link placement → Editorial review
```

### Детальное описание

#### Этапы 1-5: Сбор и подготовка данных

**1. Поиск (Search)**
- Firecrawl Search API находит 20 релевантных URL
- Широкий охват по теме без ограничений

**2. Парсинг (Scrape)**
- Извлечение контента с найденных сайтов
- Обработка 18-19 из 20 источников (успешность ~95%)

**3. Оценка (Score)**
- Ранжирование по формуле: `Trust×0.5 + Relevance×0.3 + Depth×0.2`
- Анализ домена, контента, глубины

**4. Отбор (Select)**
- Выбор топ-5 лучших источников
- Минимальная длина: 10,000 символов

**5. Очистка (Clean)**
- Удаление навигации, рекламы, мусора
- Извлечение чистого текста

#### Этапы 6-8: Структурирование и генерация

**6. Извлечение структур (Extract Prompts)**
- DeepSeek анализирует КАЖДЫЙ из 5 источников отдельно
- Создает 5 независимых структур статьи

**7. Ultimate Structure**
- Объединение 5 структур в одну оптимальную
- Добавление FAQ блоков и списка источников

**8. Генерация (Generate Article)**
- Посекционная генерация контента
- DeepSeek FREE модель
- Нумерованные ссылки на источники [1]-[5]

#### Этапы 9-12: Обогащение контента

**9. Перевод по секциям (Translation)**
- Посекционный перевод каждой секции отдельно
- DeepSeek FREE модель
- Валидация качества и словарная проверка
- Сохранение оригинала для каждой секции

**10. Факт-чекинг (Fact-Check)**
- Google Gemini с нативным веб-поиском
- Проверка фактов на ПЕРЕВЕДЕННОМ тексте
- 10+ поисковых запросов на проверку
- Работа с секциями на целевом языке

**11. Расстановка ссылок (Link Placement)**
- Автоматическое добавление 10-20 авторитетных ссылок
- Ссылки подбираются для ЦЕЛЕВОГО ЯЗЫКА
- Приоритет: docs.* → arxiv.org → github.com
- Умное позиционирование в тексте

**12. Редакторский обзор (Editorial Review)**
- Финальная обработка для WordPress
- Оптимизация SEO полей
- Исправление форматирования
- WordPress публикация (опционально)

---

## 🎛️ Переменные и кастомизация

Система переменных позволяет кастомизировать генерацию через CLI аргументы.

### Доступные переменные

#### author_style (string)
Стиль написания статьи.

**Этап**: generate_article

```bash
python3 main.py "тема" --author-style "technical"
python3 main.py "тема" --author-style "academic"
python3 main.py "тема" --author-style "business"
```

#### target_audience (string)
Целевая аудитория материала.

**Этап**: generate_article

```bash
python3 main.py "тема" --target-audience "разработчики"
python3 main.py "тема" --target-audience "менеджеры"
python3 main.py "тема" --target-audience "начинающие"
```

#### theme_focus (string)
Фокус на конкретной тематике.

**Этап**: generate_article

```bash
python3 main.py "ИИ" --theme-focus "computer vision"
python3 main.py "программирование" --theme-focus "веб-разработка"
```

#### tone_of_voice (string)
Тон повествования.

**Этап**: generate_article

```bash
python3 main.py "тема" --tone-of-voice "formal"
python3 main.py "тема" --tone-of-voice "casual"
python3 main.py "тема" --tone-of-voice "professional"
```

#### article_length (number)
Целевая длина статьи в символах.

**Этап**: editorial_review

```bash
python3 main.py "тема" --article-length 5000
python3 main.py "тема" --article-length 10000
```

#### language (string)
Язык написания материала.

**Этапы**: generate_article, translation, editorial_review

```bash
python3 main.py "тема" --language "русский"   # По умолчанию
python3 main.py "тема" --language "english"
python3 main.py "тема" --language "spanish"
```

#### custom_requirements (string)
Дополнительные требования к контенту.

**Этап**: create_structure

```bash
python3 main.py "тема" --custom-requirements "Больше примеров кода"
python3 main.py "тема" --custom-requirements "Добавить сравнительную таблицу"
```

### Комбинирование переменных

```bash
# Полная кастомизация
python3 main.py "prompt injection защита" \
  --author-style "technical" \
  --theme-focus "cybersecurity" \
  --target-audience "разработчики" \
  --tone-of-voice "professional" \
  --language "русский" \
  --article-length 7000 \
  --custom-requirements "Больше реальных примеров атак"
```

### Логические переменные

#### fact_check_mode (on/off)
Включение/отключение факт-чекинга.

```bash
# Без факт-чека (быстрее, но менее точно)
python3 main.py "тема" --fact-check-mode off

# С факт-чеком (по умолчанию)
python3 main.py "тема" --fact-check-mode on
```

#### link_placement_mode (on/off)
Включение/отключение расстановки ссылок.

```bash
# Без внешних ссылок
python3 main.py "тема" --link-placement-mode off

# С внешними ссылками (по умолчанию)
python3 main.py "тема" --link-placement-mode on
```

---

## 🔧 Режимы работы

### 1. Одиночная генерация

Генерация одной статьи по теме.

```bash
# Базовая команда
python3 main.py "тема статьи"

# С переменными
python3 main.py "тема" --author-style "technical" --language "english"

# Без публикации
python3 main.py "тема" --skip-publication
```

### 2. Пакетная обработка

Массовая генерация списка тем.

#### Создание файла тем

Создайте текстовый файл с темами (одна на строку):

```
# topics.txt
API автоматизация в 2024
Машинное обучение для начинающих
Кибербезопасность в облаке
Prompt engineering best practices
```

#### Запуск batch processor

```bash
# Базовая пакетная обработка
python3 batch_processor.py topics.txt

# Без публикации в WordPress
python3 batch_processor.py topics.txt --skip-publication

# С возобновлением прерванной обработки
python3 batch_processor.py topics.txt --resume

# С кастомными моделями
python3 batch_processor.py topics.txt --generate-model "deepseek-reasoner"

# С переменными для кастомизации контента
python3 batch_processor.py topics_guides.txt \
  --content-type guides \
  --author-style "technical" \
  --theme-focus "cybersecurity" \
  --target-audience "разработчики" \
  --tone-of-voice "professional" \
  --language "русский" \
  --article-length 7000 \
  --fact-check-mode off \
  --link-placement-mode off \
  --translation-mode off
```

### 3. Запуск с определенного этапа

Продолжение pipeline с конкретного этапа (для отладки или пропуска начальных этапов).

#### Доступные стадии

##### generate_article (этап 8)
Генерация статьи из готовой структуры.

```bash
python3 main.py "тема" --start-from-stage generate_article
```

**Требуется**: `07_ultimate_structure/ultimate_structure.json`

**Создает**: `08_article_generation/wordpress_data.json`

---

##### translation (этап 9)
Перевод секций на целевой язык.

```bash
python3 main.py "тема" --start-from-stage translation --language "english"
```

**Требуется**: `08_article_generation/wordpress_data.json`

**Создает**: `09_translation/translated_sections.json`

---

##### fact_check (этап 10)
Проверка фактов через Google Gemini с веб-поиском.

```bash
python3 main.py "тема" --start-from-stage fact_check
```

**Требуется**: `09_translation/translated_sections.json`

**Создает**: `10_fact_check/fact_checked_content.json`

---

##### link_placement (этап 11)
Добавление 10-20 внешних ссылок в контент.

```bash
python3 main.py "тема" --start-from-stage link_placement
```

**Требуется**: `09_translation/translated_sections.json`

**Создает**: `11_link_placement/content_with_links.json`

---

##### editorial_review (этап 12)
Финальная редактура и форматирование для WordPress.

```bash
python3 main.py "тема" --start-from-stage editorial_review
```

**Требуется**: `11_link_placement/content_with_links.json` (или `10_fact_check/` или `09_translation/`)

**Создает**: `12_editorial_review/wordpress_data_final.json`

---

##### publication (этап 13)
Публикация в WordPress.

```bash
python3 main.py "тема" --start-from-stage publication
```

**Требуется**: `12_editorial_review/wordpress_data_final.json`

**Создает**: `wordpress_publication_result.json`

---

**Важно**: Команда ищет существующую папку `output/{тема}/` и использует данные оттуда. Запускайте полный pipeline хотя бы раз для создания необходимых файлов.

### 4. Типы контента

#### basic_articles (по умолчанию)
Информационные статьи с FAQ блоками и источниками.

```bash
python3 main.py "API testing tools" --content-type basic_articles
```

**Особенности**:
- FAQ разделы с `<details><summary>`
- Нумерованные источники [1]-[5]
- 10-20 внешних ссылок
- 12 этапов пайплайна + WordPress (опционально)

#### guides
Пошаговые руководства и туториалы.

```bash
python3 main.py "Установка DeepSeek локально" --content-type guides
```

**Особенности**:
- Пошаговая структура
- Технические инструкции
- Примеры команд

---

## 📊 Логирование и мониторинг

Content Factory поддерживает два режима логирования: тихий (по умолчанию) и детальный (verbose).

### Тихий режим (по умолчанию)

Показывает только ключевые события.

```bash
python3 main.py "тема"
python3 batch_processor.py topics.txt
```

**Что показывается**:
```
2025-10-03 14:16:52 [INFO] - Starting pipeline for topic: 'AI trends'
2025-10-03 14:16:54 [INFO] - Found 20 results from search
2025-10-03 14:17:35 [INFO] - Successfully scraped 18 out of 19 URLs
2025-10-03 14:17:36 [INFO] - Selected top 5 sources
...
2025-10-03 14:29:42 [INFO] - ✅ Pipeline completed successfully
```

### Verbose режим

Детальное логирование для отладки.

```bash
python3 main.py "тема" --verbose
python3 batch_processor.py topics.txt --verbose
```

**Что добавляется**:
- URL каждого источника
- Детали retry попыток
- Информация о моделях LLM
- Размеры контента
- Технические детали парсинга

**Пример**:
```
2025-10-03 14:16:54 [DEBUG] - Scraping URL: https://example.com/article1
2025-10-03 14:16:55 [DEBUG] - Content length: 15234 chars
2025-10-03 14:16:56 [DEBUG] - Trust score: 0.85, Relevance: 0.92
...
```

### Логи и артефакты

Все логи и данные сохраняются в `output/{topic}/`:

```
output/your_topic/
├── 01_search/
│   ├── search_results.json
│   └── filtered_urls.json
├── 02_scrape/
│   ├── scraped_content.json
│   └── failed_urls.txt
├── 09_fact_check/
│   ├── fact_checked_content.json
│   └── llm_responses_raw/
├── 12_translation/
│   └── translated_content.json
├── 13_editorial_review/
│   └── wordpress_data_final.json
└── token_usage_report.json
```

### Предупреждения о факт-чеке

Если fact-check не удался, в конце pipeline появится предупреждение:

```
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
⚠️  FINAL WARNING: Article contains UNVERIFIED CONTENT
Fact-check failed for 2 groups
Manual fact verification recommended before publication
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
```

---

## 📈 Производительность и оптимизация

### Время выполнения

- **Полный pipeline**: ~12-17 минут
- **Без fact-check**: ~10-12 минут
- **Без link placement**: ~10-12 минут
- **Только генерация** (этапы 1-8): ~8-10 минут

### Использование токенов

- **Средний расход**: 45-55k tokens на статью
- **С длинными статьями**: 60-70k tokens
- **Распределение**:
  - Генерация: 30-40k
  - Fact-check: 10-15k
  - Editorial: 5-10k

### Batch processing

При пакетной обработке система автоматически оптимизирует память:

- Принудительная сборка мусора между темами
- Очистка HTTP соединений
- Сброс token tracker
- Мониторинг использования памяти

**Лимит памяти**: 2GB на процесс

---

## 🔧 Полезные команды

### Базовые команды

```bash
# Простая генерация
python3 main.py "тема"

# С переменными
python3 main.py "тема" --author-style "technical" --language "english"

# Batch обработка
python3 batch_processor.py topics.txt

# С этапа
python3 main.py "тема" --start-from-stage fact_check
```

### Управление этапами

```bash
# Без факт-чека
python3 main.py "тема" --fact-check-mode off

# Без link placement
python3 main.py "тема" --link-placement-mode off

# Без публикации
python3 main.py "тема" --skip-publication
```

### Отладка

```bash
# Verbose режим
python3 main.py "тема" --verbose

# Запуск с этапа для отладки
python3 main.py "тема" --start-from-stage editorial_review --verbose
```

---

## 📚 Дополнительная документация

- **[TECHNICAL.md](TECHNICAL.md)** - Техническая документация, API, архитектура
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - FAQ и решение проблем
- **[config.md](config.md)** - Полный справочник по конфигурации
- **[../CHANGELOG.md](../CHANGELOG.md)** - История версий и изменений

---

**Версия**: 2.3.0 | **Статус**: ✅ Production Ready
