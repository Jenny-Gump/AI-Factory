# 🔗 Link Processing - Система автоматических ссылок

## 📖 Обзор

Система автоматически добавляет авторитетные внешние ссылки в сгенерированные статьи через 4-этапный пайплайн. Находит места где читатель может захотеть ПРОВЕРИТЬ или ИЗУЧИТЬ ГЛУБЖЕ тему и вставляет 10-20 релевантных ссылок с академическим форматированием.

## 🏗️ Архитектура системы (ПРАВИЛЬНАЯ)

### Этап 1: Link Planning (Anchor Text система)
- **Предобработка HTML**: Добавление маркеров `[HEADER_START]`, `[CODE_START]`, `[FORMAT_START]` для обозначения зон, где не следует выбирать якоря
- **LLM анализирует подготовленный HTML** с маркерами для избегания выбора текста внутри тегов
- **Находит конкретные фрагменты текста** (`anchor_text`) только в обычном тексте, избегая:
  - Заголовки (`<h1>`, `<h2>`, `<h3>`)
  - Код (`<code>`, `<pre>`)
  - Форматирование (`<strong>`, `<em>`)
- **Создает 10-20 поисковых запросов** для каждого `anchor_text`
- **Определяет контекст** до и после каждого фрагмента (`context_before`, `context_after`)
- **Модель**: `deepseek-chat` с fallback на Gemini
- **Промпт**: `prompts/basic_articles/01_5_link_planning.txt` с правилами выбора якорей
- **Выход**: JSON с массивом `{"ref_id": 1, "anchor_text": "Least-to-Most техника", "query": "least to most prompting research", "context_before": "метод ", "context_after": " является"}`

### Этап 2: Anchor Validation
- **Упрощенная проверка** только `anchor_text` без строгого контекста
- **Двухуровневый поиск с ленивым fallback**:
  1. **Первичный поиск**: Ищет anchor_text в оригинальном HTML напрямую (bs4 НЕ используется)
  2. **Опциональный fallback**: Только если не найдено в HTML:
     - Проверяет наличие BeautifulSoup4 (импорт по требованию)
     - Если bs4 доступен - парсит HTML и ищет в нормализованном тексте
     - Если bs4 НЕ установлен - пропускает этот шаг, anchor помечается как не найденный
- **Функция**: `_validate_anchors()` с ленивой инициализацией BeautifulSoup
- **Оптимизация**: BeautifulSoup создается только при первой необходимости и кэшируется
- **Логирование**: Отчет о валидных/невалидных анкорах + статус использования bs4
- **Поведение при ошибке**:
  - Если bs4 не установлен - система работает без fallback
  - Невалидные якоря исключаются из обработки

### Этап 3: Search Candidates
- **Firecrawl Search API** ищет по каждому `query` (лимит 5 результатов на запрос)
- **Фильтрация доменов** по белому/черному списку из `filters/preferred_domains.json`
- **HEAD проверка** доступности ссылок (2s timeout)
- **Последовательная обработка** запросов с задержками для избежания rate limiting
- **Выход**: `candidates_{ref_id}.json` для каждого запроса

### Этап 4: LLM Link Selection
- **LLM анализ кандидатов** для каждого `anchor_text`
- **Входные данные**: `anchor_text`, `context`, список кандидатов
- **Промпт**: `prompts/basic_articles/02_link_selection.txt` ✅ **ИСПОЛЬЗУЕТСЯ КОРРЕКТНО**
- **Модель**: `deepseek-chat` для выбора лучшей ссылки
- **Приоритет**: docs.* > научные статьи > GitHub > остальные
- **Выход**: `selected_links.json` с лучшими ссылками

### Этап 5: Smart Positioning & Apply Links
- **Умный поиск позиций** через `_find_best_insertion_point()`
- **Поиск по anchor_text** с учетом контекста до/после
- **Вставка маркеров** `[1]` после найденного `anchor_text`
- **Замена на HTML** ссылки с академическим форматированием
- **Создание раздела "Полезные ссылки"** внизу статьи
- **Валидация HTML** структуры на корректность

## 🔧 Архитектурные особенности Anchor Text системы (September 2025)

### ✅ Ключевые принципы работы:

#### 1. Anchor Text позиционирование (НЕ позиции символов!)
```python
def _find_best_insertion_point(self, text: str, anchor_text: str, context_before: str, context_after: str) -> int:
    # Поиск точной фразы с контекстом
    search_pattern = context_before + anchor_text + context_after
    pattern_pos = text.find(search_pattern)

    if pattern_pos != -1:
        # Вычисление позиции ПОСЛЕ anchor_text
        anchor_start = pattern_pos + len(context_before)
        anchor_end = anchor_start + len(anchor_text)
        return self._adjust_position_to_avoid_tags(text, anchor_end)
```

#### 2. Предобработка HTML для LLM
```python
def _prepare_html_for_llm(self, html_content: str) -> str:
    # Помечает элементы для избегания при выборе якорей
    content = content.replace('<h2>', '[HEADER_START]<h2>')
    content = content.replace('</h2>', '</h2>[HEADER_END]')
    content = content.replace('<code>', '[CODE_START]<code>')
    content = content.replace('</code>', '</code>[CODE_END]')
    content = content.replace('<strong>', '[FORMAT_START]<strong>')
    content = content.replace('</strong>', '</strong>[FORMAT_END]')
```

#### 3. Упрощенная валидация якорей
```python
def _validate_anchors(self, html_content: str, link_plan: List[Dict]) -> Dict:
    # Двухуровневый поиск anchor_text
    soup = BeautifulSoup(html_content, 'html.parser')
    clean_text_normalized = ' '.join(soup.get_text().split())

    # Сначала ищем в HTML
    if anchor_text in html_content:
        # Найдено в оригинале
    # Затем fallback в нормализованном тексте
    elif anchor_normalized in clean_text_normalized:
        # Найдено в чистом тексте
```

#### 4. LLM анализ для выбора ссылок
```python
messages = _load_and_prepare_messages(
    "basic_articles",
    "02_link_selection",  # ✅ ФАЙЛ prompts/basic_articles/02_link_selection.txt ИСПОЛЬЗУЕТСЯ КОРРЕКТНО!
    {
        "anchor_text": link_item.get("anchor_text", ""),
        "context": f"{context_before} {context_after}",
        "candidates": json.dumps(candidates, indent=2)
    }
)
```

#### 5. Последовательная обработка по ref_id
```python
# Этап 1: Создание плана с anchor_text
link_plan = [
    {
        "ref_id": "1",
        "anchor_text": "Least-to-Most техника",
        "query": "least to most prompting research arxiv",
        "context_before": "метод ",
        "context_after": " является",
        "hint": "Научная статья о LTM промптинге"
    }
]

# Этап 2: Поиск кандидатов для каждого ref_id
for plan in link_plan:
    candidates = firecrawl_search(plan["query"])
    # Сохранение в candidates_{ref_id}.json

# Этап 3: LLM выбор лучшей ссылки
for ref_id, candidates in all_candidates.items():
    selected = llm_select_best_link(anchor_text, context, candidates)
    # ✅ ИСПОЛЬЗУЕТ 02_link_selection.txt КОРРЕКТНО!

# Этап 4: Умная вставка после anchor_text
for plan in validated_plans:
    position = _find_best_insertion_point(
        content, plan["anchor_text"],
        plan["context_before"], plan["context_after"]
    )
    # Вставка [ref_id] в найденную позицию
```

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
```json
{
  "priority_domains": [
    "docs.microsoft.com", "developer.mozilla.org",
    "docs.github.com", "developers.google.com",
    "w3.org", "ietf.org", "arxiv.org",
    "openreview.net", "papers.nips.cc"
  ],
  "blocked_domains": [
    "reddit.com", "stackoverflow.com", "medium.com",
    "dev.to", "blogger.com", "quora.com"
  ],
  "priority_paths": [
    "/docs", "/documentation", "/api", "/reference",
    "/guide", "/tutorial", "/spec", "/standards"
  ]
}
```

## 🚀 Использование

### В основном пайплайне:
```bash
# main.py всегда использует basic_articles_pipeline с автоматическими ссылками
python3 main.py "JavaScript best practices"

# Для коллекций промптов (без ссылок)
python3 batch_processor.py topics_file.txt --content-type prompt_collection
```

### Интеграция в код:
```python
from src.link_processor import LinkProcessor

processor = LinkProcessor()
result = processor.process_links(
    wordpress_data=wordpress_data,
    topic="Machine Learning trends 2024",
    base_path="output/article",
    token_tracker=tracker,
    active_models=active_models
)
```

## 📁 Артефакты

После обработки создаются файлы в `output/article/10_link_processing/`:
- `link_plan.json` - план размещения ссылок от LLM
- `draft_with_markers.html` - HTML с маркерами [1]..[N]
- `candidates.json` - найденные кандидаты от Firecrawl
- `selected_links.json` - выбранные ссылки с оценками
- `article_with_links.html` - финальная статья с ссылками
- `links_report.json` - отчет о процессе
- `marker_insertions_debug.json` - отладочная информация
- `llm_responses_raw/link_plan_response.txt` - сырой ответ LLM

## 📊 Результат работы

**До обработки**:
```html
<p>Техника Least-to-Most промптинга — это подход взаимодействия с ИИ.</p>
```

**После обработки**:
```html
<p>Техника Least-to-Most промптинга<a id="cite-1" href="#ref-1" rel="nofollow">[1]</a> — это подход взаимодействия с ИИ.</p>

<h2>Полезные ссылки</h2>
<ol>
  <li id="ref-1">
    <a href="https://arxiv.org/abs/2205.10625" target="_blank" rel="nofollow noopener">
      [2205.10625] Least-to-Most Prompting Enables Complex Reasoning
    </a>
    <a href="#cite-1" aria-label="Вернуться к месту ссылки [1]">[↑]</a>
  </li>
</ol>
```

## 🔍 Отладка и мониторинг

### Типичный лог успешной обработки:
```
=== Starting Link Processing Pipeline ===
Step 1: Creating link plan...
✓ Generated 12 link queries with markers
Step 2: Searching for link candidates...
✓ Found 45 total candidates across 12 queries
Step 3: Selecting best links...
✓ Selected 10/12 links
Step 4: Applying links to content...
✓ Applied 10 sequential academic footnotes to content
Link processing report: 10/12 resolved (83.3%)
=== Link Processing Complete (42.3s) ===
```

### Проблемы и решения:

**"No markers found in headers"** ✅ **ИСПРАВЛЕНО**
- Система автоматически перемещает маркеры из заголовков в текст

**"No nested anchor tags found"** ✅ **ИСПРАВЛЕНО**
- Исключено дублирование через простые маркеры [N]

**"Failed to parse link plan JSON"** ✅ **ИСПРАВЛЕНО**
- Добавлен fallback механизм для обработки markdown блоков

**"Link processing failed"** - Система возвращает оригинальный контент
- Проверить логи каждого этапа в `logs/operations.jsonl`
- Проверить конфигурацию Firecrawl API ключа

## 📈 Метрики качества

**Цель**: >70% success rate для качественной статьи

**Типичные показатели**:
- **Найдено ссылок**: 85-95% от запланированных
- **Качество источников**: 70%+ официальные/научные
- **Время обработки**: 30-60 секунд
- **HTML валидность**: 100% (после исправлений)

**Статус системы**: ✅ **ПОЛНОСТЬЮ РАБОТАЕТ**

## 📦 Зависимости

### Обязательные:
- **Firecrawl API** - для поиска кандидатов ссылок
- **LLM API** (DeepSeek/Gemini) - для генерации и выбора ссылок

### Опциональные:
- **beautifulsoup4** - для fallback валидации anchor текстов
  - Если установлен: улучшенная валидация через нормализованный текст
  - Если НЕ установлен: система работает, но без fallback для сложных случаев
  - Установка: `pip install beautifulsoup4`

## 🧪 Тестирование

### Тест работы без BeautifulSoup:
```bash
pip uninstall beautifulsoup4 -y
python -c "from src.link_processor import LinkProcessor; print('✅ Работает без bs4')"
```

### Тест fallback с BeautifulSoup:
```bash
pip install beautifulsoup4
python test_link_fixes.py
```

Ожидаемый результат:
```
✓ Generated X link positions
✓ No markers found in headers
✓ No nested anchor tags found
✓ Final content has no nested anchor tags
```

---

**Последнее обновление**: 20 сентября 2025 - Исправлена проблема JSON парсинга DeepSeek модели
**Статус**: ✅ **ПОЛНОСТЬЮ ИСПРАВЛЕНО** - Система автоматически исправляет JSON ошибки с ретраями
**Внимание**: Добавлена логика 2-х попыток LLM перед fallback парсингом

## ✅ ИСПРАВЛЕНИЯ В НОВОЙ ВЕРСИИ (September 20, 2025)

### Устраненные проблемы:
1. **JSON парсинг DeepSeek модели**: Исправлена ошибка "Expecting ':' delimiter" из-за отсутствующих двоеточий
2. **Система ретраев**: Добавлена логика 2-х попыток LLM запроса перед использованием fallback парсинга
3. **Усиленный промпт**: Добавлены строгие требования к JSON формату для предотвращения ошибок
4. **Автоматическое исправление**: JSON парсер автоматически исправляет типичные ошибки DeepSeek модели

### Финальная схема с ретраями (СООТВЕТСТВУЕТ КОДУ):
1. **Link Planning с ретраями**:
   - Попытка 1: LLM запрос + базовое исправление JSON
   - Попытка 2: Повторный LLM запрос при ошибке JSON
   - Fallback: Расширенный JSON парсер с исправлением DeepSeek ошибок
2. **Автоматическое исправление JSON**:
   - Исправление отсутствующих двоеточий (`"context_after: "` → `"context_after": "`)
   - Валидация структуры и обязательных полей
3. **Search Candidates**: Firecrawl поиск по каждому `query` (синхронная обработка с задержками)
4. **LLM Selection**: ✅ **ИСПОЛЬЗУЕТ ПРАВИЛЬНЫЙ 02_link_selection.txt**
5. **Smart Positioning**: Поиск позиции ПОСЛЕ найденного `anchor_text`
6. **Apply Links**: Замена маркеров на академические ссылки с правильной нумерацией

## 🔄 АРХИТЕКТУРНЫЕ ИЗМЕНЕНИЯ (September 2025)

### September 20, 2025 - Улучшение выбора и валидации якорей
**Изменения**:
- Добавлена предобработка HTML с маркерами для избегания выбора якорей в тегах
- Упрощена валидация - только проверка anchor_text без строгого контекста
- Добавлен fallback через BeautifulSoup для поиска в нормализованном тексте
- Обновлен промпт с правилами избегания HTML тегов (h2, h3, code, strong, em)

### September 20, 2025 - Исправление JSON парсинга DeepSeek модели
**КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ**: Полностью решена проблема "Expecting ':' delimiter":
- Добавлена система 2-х попыток LLM запроса перед fallback
- Автоматическое исправление отсутствующих двоеточий в JSON ключах
- Усиленный промпт с требованиями к корректному JSON формату
- Валидация структуры link_plan и обязательных полей
- Протестировано на реальных поврежденных JSON файлах от DeepSeek

### September 20, 2025 - Синхронная архитектура
**ВАЖНО**: Система полностью переведена на **синхронную архитектуру**:
- Убраны все `async/await` из LinkProcessor
- Последовательное выполнение этапов без event loop конфликтов
- Простой линейный пайплайн без deadlock'ов

## 📚 См. также

- **[link_scoring_system.md](link_scoring_system.md)** - Детальное описание алгоритма оценки ссылок
- **[flow.md](flow.md#этап-105-link-processing-обработка-ссылок-)** - Link Processing в контексте пайплайна
- **[troubleshooting.md](troubleshooting.md#link-processing-json-parsing-fixed-in-latest-update)** - Решение проблем с обработкой ссылок