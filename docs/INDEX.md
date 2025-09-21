# Content Factory Documentation Index

Полная документация для Content Factory - автоматизированного пайплайна генерации контента.

## Навигация по документации

### Основные руководства
- **[flow.md](flow.md)** - Детальное описание всех 11 этапов пайплайна с диагностикой
- **[troubleshooting.md](troubleshooting.md)** - Решение проблем, отладка и оптимизация

### Интеграции и настройка
- **[WORDPRESS_INTEGRATION.md](WORDPRESS_INTEGRATION.md)** - WordPress публикация и SEO настройки
- **Конфигурация** - API ключи и модели описаны в `src/config.py`

### Специализированные системы
- **[link_processing.md](link_processing.md)** - Система автоматической вставки ссылок
- **[link_scoring_system.md](link_scoring_system.md)** - Алгоритм оценки и отбора ссылок
- **[section-by-section-implementation.md](section-by-section-implementation.md)** - Реализация посекционной генерации

### История и обновления
- **[CHANGELOG.md](CHANGELOG.md)** - История изменений проекта

## Основные разделы


## Структура пайплайна (кратко)

**11 этапов обработки:**
1. Поиск источников (Search)
2. Парсинг контента (Parse)
3. Оценка качества (Score)
4. Отбор лучших (Select)
5. Очистка текста (Clean)
6. Извлечение структур (Extract)
7. Создание единой структуры (Ultimate Structure)
8. Генерация по секциям (Generate)
9. Редакторский обзор (Editorial)
10.5. Добавление ссылок (Link Processing)
11. Публикация в WordPress (Publish)

Подробное описание каждого этапа см. [flow.md](flow.md)

## Техническая информация

- **Модели LLM**: DeepSeek FREE (основная) + Gemini 2.5 (fallback)
- **API интеграции**: Firecrawl, OpenRouter, WordPress REST API
- **Языки**: Python 3.8+, поддержка русского языка
- **Время выполнения**: ~8-10 минут на статью

## Обновление документации

При обновлении документации:
1. Обновите соответствующий .md файл
2. Добавьте запись в [CHANGELOG.md](CHANGELOG.md)
3. Проверьте, что все ссылки работают
4. Синхронизируйте номера этапов если меняете пайплайн