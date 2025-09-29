# Content Factory Documentation

Автоматизированный пайплайн генерации контента на основе AI.

## 📚 Основная документация

### [flow.md](flow.md)
Детальное описание всех 11 этапов пайплайна с инструкциями по диагностике и troubleshooting.

### [config.md](config.md)
Настройка API ключей, моделей LLM, параметров производительности и интеграций.

### [WORDPRESS_INTEGRATION.md](WORDPRESS_INTEGRATION.md)
WordPress публикация, SEO настройки и REST API интеграция.

### [LOGGING.md](LOGGING.md)
Система логирования: тихий и verbose режимы, фильтрация сообщений, предупреждения о факт-чеке.

## 🎯 Быстрый старт

### Одиночная генерация:
```bash
cd "Desktop/AI DEV/Content-factory"
python main.py "Ваша тема для статьи"
```

### Batch обработка:
```bash
python batch_processor.py topics.txt --content-type basic_articles
```

## 🔧 Режимы логирования

### Обычный режим (тихий):
```bash
python main.py "Ваша тема"                    # Только ключевые этапы
python batch_processor.py topics.txt         # Тихий batch режим
```

### Verbose режим (детальный):
```bash
python main.py "Ваша тема" --verbose          # Все детали и отладка
python batch_processor.py topics.txt --verbose # Детальный batch
```

**Подробнее**: См. [LOGGING.md](LOGGING.md) для полного описания системы логирования

## 📊 Структура пайплайна

1. **Поиск** - Firecrawl Search API (20 источников)
2. **Парсинг** - Извлечение контента из найденных URL
3. **Оценка** - Трастовость, релевантность, глубина
4. **Отбор** - Топ-5 лучших источников
5. **Очистка** - Удаление мусора из текста
6. **Извлечение** - Анализ структур из источников
7. **Структура** - Создание единой структуры статьи
8. **Генерация** - Посекционная генерация контента
9. **Факт-чекинг** - Проверка фактов через Google Gemini с нативным веб-поиском
10. **Редактура** - Финальная проверка и улучшение (с продвинутой retry системой + исправление переносов строк)
11. **Публикация** - Отправка в WordPress

## 🛠 Типы контента

### basic_articles
- Информационные статьи с FAQ
- Промпты в `prompts/basic_articles/`
- Категория WordPress: articles

### guides
- Пошаговые руководства
- Промпты в `prompts/guides/`
- Категория WordPress: guides

## ⚙️ Технические детали

- **LLM**: DeepSeek Chat v3.1 FREE + **Google Gemini 2.5 Flash (fact-check)** + DeepSeek (fallback)
- **🆕 Retry система**: 3×3 попытки с автоматическим fallback между моделями
- **🆕 JSON нормализация**: 4-уровневая система восстановления поврежденных ответов
- **🆕 Исправление переносов строк**: Автоматическое исправление `\\n` → реальные переносы для WordPress
- **API**: Firecrawl, OpenRouter, WordPress REST
- **Время**: ~10-12 минут на статью (с fact-checking и retry логикой)
- **Python**: 3.8+

## 📁 Структура проекта

```
Content-factory/
├── src/              # Основные модули
├── prompts/          # Промпты для разных типов контента
│   ├── basic_articles/  # Промпты для информационных статей
│   └── guides/          # Промпты для руководств
├── output/           # Результаты генерации
├── filters/          # Фильтры доменов
├── docs/             # Документация
├── main.py           # Одиночная генерация
├── batch_processor.py # Batch обработка
└── batch_config.py   # Конфигурация batch processor
```