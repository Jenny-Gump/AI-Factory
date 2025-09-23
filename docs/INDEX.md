# Content Factory Documentation

Автоматизированный пайплайн генерации контента на основе AI.

## 📚 Основная документация

### [flow.md](flow.md)
Детальное описание всех 11 этапов пайплайна с инструкциями по диагностике и troubleshooting.

### [config.md](config.md)
Настройка API ключей, моделей LLM, параметров производительности и интеграций.

### [WORDPRESS_INTEGRATION.md](WORDPRESS_INTEGRATION.md)
WordPress публикация, SEO настройки и REST API интеграция.

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

## 📊 Структура пайплайна

1. **Поиск** - Firecrawl Search API (20 источников)
2. **Парсинг** - Извлечение контента из найденных URL
3. **Оценка** - Трастовость, релевантность, глубина
4. **Отбор** - Топ-5 лучших источников
5. **Очистка** - Удаление мусора из текста
6. **Извлечение** - Анализ структур из источников
7. **Структура** - Создание единой структуры статьи
8. **Генерация** - Посекционная генерация контента
9. **Редактура** - Финальная проверка и улучшение
10. **Ссылки** - Автоматическая вставка релевантных ссылок
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

- **LLM**: DeepSeek Chat v3.1 FREE + Gemini 2.5 Flash (fallback)
- **API**: Firecrawl, OpenRouter, WordPress REST
- **Время**: ~8-10 минут на статью
- **Python**: 3.8+

## 📁 Структура проекта

```
Content-factory/
├── src/              # Основные модули
├── prompts/          # Промпты для разных типов контента
├── output/           # Результаты генерации
├── filters/          # Фильтры доменов
├── main.py           # Одиночная генерация
└── batch_processor.py # Batch обработка
```