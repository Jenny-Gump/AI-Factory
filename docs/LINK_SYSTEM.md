# Система автоматических ссылок

## 🔗 Обзор

Система автоматически добавляет авторитетные ссылки в статьи через 4-этапный пайплайн обработки ссылок.

## 📋 Как это работает

### Этап 1: Link Planning (`01_5_link_planning.txt`)
- **LLM анализирует HTML контент** статьи на предмет утверждений и концепций
- **Находит места** где читатель может захотеть ПРОВЕРИТЬ или ИЗУЧИТЬ ГЛУБЖЕ тему
- **Создает 5-15 поисковых запросов** для поиска пруфов и дополнительных материалов
- **Расставляет маркеры [1]..[N]** в HTML где читатель скажет "а где об этом почитать подробнее?"
- **Выдает JSON** с `link_plan` и `draft_with_markers`
- **Использует FREE модель** `deepseek/deepseek-chat-v3.1:free` с fallback на Gemini 2.5

### Этап 2: Search Candidates
- **Firecrawl Search API** ищет по каждому запросу (лимит 5 результатов)
- **Фильтрация доменов** по белому/черному списку
- **HEAD проверка** доступности ссылок
- **Сохранение кандидатов** в `candidates.json`

### Этап 3: Link Selection
- **Heuristic scoring** по приоритетным доменам и путям
- **LLM tiebreaker** для выбора лучших ссылок при равных оценках
- **Выбор финального URL** для каждого маркера [N]

### Этап 4: Apply Links
- **Замена маркеров** на HTML ссылки: `<a href="..." rel="nofollow noopener" target="_blank">[N]</a>`
- **Удаление старых разделов "Источники"** (ссылки теперь inline)
- **Сохранение финального HTML** с интегрированными ссылками

## ⚙️ Конфигурация

### Основные настройки (`src/config.py`):
```python
LINK_PROCESSING_ENABLED = True  # Включить/выключить систему ссылок
LINK_MAX_QUERIES = 15          # Максимум поисковых запросов на статью
LINK_MAX_CANDIDATES_PER_QUERY = 5  # Максимум кандидатов на запрос
LINK_PROCESSING_TIMEOUT = 360      # Таймаут всего процесса (6 минут)
```

### Фильтрация доменов (`filters/preferred_domains.json`):

**Приоритетные домены** (высокий scoring):
- `docs.microsoft.com`, `developer.mozilla.org`
- `docs.github.com`, `developers.google.com`
- `w3.org`, `ietf.org`, `arxiv.org`
- Паттерны: `docs.`, `developer.`, `api.`

**Заблокированные домены**:
- `reddit.com`, `stackoverflow.com`, `medium.com`
- `dev.to`, `blogger.com`, `quora.com`

**Приоритетные пути**:
- `/docs`, `/documentation`, `/api`, `/reference`
- `/guide`, `/tutorial`, `/spec`, `/standards`

## 🚀 Использование

### Для статей с автоматическими ссылками:
```bash
# main.py всегда использует basic_articles_pipeline (информационные статьи с FAQ)
python3 main.py "JavaScript best practices"

# Для коллекций промптов используйте batch_processor.py с --content-type
python3 batch_processor.py topics_file.txt --content-type prompt_collection --skip-publication
```

### Интеграция в пайплайн:

**basic_articles_flow**: Этап 10.5 (строки 244-278 в main.py)
**main_flow**: Этап 8.5 (строки 511-544 в main.py)

## 📁 Артефакты

После обработки создаются файлы:
- `08_5_links/link_plan.json` - план размещения ссылок
- `08_5_links/draft_with_markers.html` - HTML с маркерами [1]..[N]
- `08_5_links/candidates.json` - найденные кандидаты
- `08_5_links/selected_links.json` - выбранные ссылки
- `08_5_links/article_with_links.html` - финальная статья с ссылками
- `08_5_links/links_report.json` - отчет о процессе

## 🎯 Результат

**До обработки**:
```html
<p>JavaScript использует переменные для хранения данных.</p>
```

**После обработки**:
```html
<p>JavaScript <a href="https://developer.mozilla.org/docs/Web/JavaScript/Guide/Grammar_and_types#Variables" rel="nofollow noopener" target="_blank">[1]</a> использует переменные для хранения данных.</p>
```

## 🔧 Отладка

### Логи процесса:
```
=== Starting Link Processing Stage ===
Step 1: Creating link plan...
Step 2: Searching for link candidates...
Step 3: Selecting best links...
Step 4: Applying links to content...
Link processing report: 8/10 resolved (80%)
```

### Типичные проблемы:

**"No link plan generated"** - LLM не смог создать план ссылок
- Проверить промпт `01_5_link_planning.txt` (новая логика "поиска пруфов")
- Проверить FREE модель `deepseek/deepseek-chat-v3.1:free` и fallback
- Проверить токены и лимиты

**"Link processing failed"** - Ошибка на любом этапе
- Система fallback вернет оригинальный контент
- Проверить логи для детальной диагностики

## 📊 Метрики качества

- **Success rate**: процент успешно разрешенных маркеров
- **Processing time**: время обработки всего процесса
- **Domains used**: статистика используемых доменов
- **Unresolved**: список нерешенных маркеров

Цель: >70% success rate для качественной статьи с ссылками.

## ✅ Статус системы: ПОЛНОСТЬЮ РАБОТАЕТ

**Последнее тестирование**: 16.09.2025
**Результат**: ✅ 100% success rate (5/5 ссылок)
**Время обработки**: 31.6 секунд

### Пример результата:
```html
<h2>React Hooks<a href="https://react.dev/reference/react/hooks" rel="nofollow noopener" target="_blank">[1]</a></h2>
<p>React hooks позволяют использовать state и другие возможности React без написания классов<a href="https://react.dev/reference/react/Component" rel="nofollow noopener" target="_blank">[5]</a>.</p>
<p>useState<a href="https://legacy.reactjs.org/docs/hooks-state.html" rel="nofollow noopener" target="_blank">[2]</a> hook позволяет добавить state в функциональные компоненты.</p>
```

### Исправленные проблемы:
- ✅ Импорты в LinkProcessor (`src/config`, `src/logger_config`, etc.)
- ✅ Дублирующий импорт модуля `re`
- ✅ Ошибки парсинга и обработки маркеров