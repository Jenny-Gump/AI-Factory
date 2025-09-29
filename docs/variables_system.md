# Система динамических переменных

## Обзор

Система динамических переменных позволяет передавать дополнительные инструкции в промпты на разных этапах пайплайна Content Factory. Система работает универсально со всеми типами контента (basic_articles, guides) и поддерживает батч-обработку.

## Архитектура

### Компоненты

1. **variables_config.json** - конфигурационный файл с определениями переменных
2. **src/variables_manager.py** - класс VariablesManager для управления переменными
3. **CLI аргументы** - интеграция с командной строкой
4. **Интеграция в пайплайн** - инъекция переменных в промпты

### Принцип работы

1. Переменные определяются в `variables_config.json` с указанием:
   - Типа данных (string, number, boolean)
   - Этапов пайплайна, на которых применяется
   - Шаблона аддона для промпта

2. VariablesManager загружает конфигурацию и управляет активными переменными

3. При загрузке промптов функция `_load_and_prepare_messages()` добавляет аддоны переменных к пользовательскому сообщению

4. Аддоны передаются в LLM как дополнительные инструкции

## Доступные переменные

### article_length (number)
- **Описание**: Целевая длина статьи в символах
- **Этапы**: editorial_review
- **Пример**: `--article-length 5000`

### author_style (string)
- **Описание**: Стиль автора для написания
- **Этапы**: generate_article
- **Пример**: `--author-style "technical"`

### theme_focus (string)
- **Описание**: Фокусировка на конкретной тематике
- **Этапы**: generate_article
- **Пример**: `--theme-focus "AI technology"`

### custom_requirements (string)
- **Описание**: Дополнительные пожелания к контенту
- **Этапы**: create_structure
- **Пример**: `--custom-requirements "Добавить больше технических деталей"`

### target_audience (string)
- **Описание**: Целевая аудитория статьи
- **Этапы**: generate_article
- **Пример**: `--target-audience "разработчики"`

### tone_of_voice (string)
- **Описание**: Тон повествования
- **Этапы**: generate_article
- **Пример**: `--tone-of-voice "formal"`

### include_examples (boolean)
- **Описание**: Включать практические примеры
- **Этапы**: отключена
- **Пример**: `--include-examples`

### seo_keywords (string)
- **Описание**: Ключевые слова для SEO
- **Этапы**: отключена
- **Пример**: `--seo-keywords "машинное обучение, ИИ, алгоритмы"`

## Использование

### Командная строка

```bash
# Простой пример
python3 main.py "Машинное обучение в производстве" --author-style "technical" --include-examples

# Полный пример со всеми переменными
python3 main.py "Нейронные сети" \
  --article-length 8000 \
  --author-style "academic" \
  --theme-focus "deep learning" \
  --custom-requirements "Больше математических формул" \
  --target-audience "исследователи" \
  --tone-of-voice "formal" \
  --include-examples \
  --seo-keywords "нейронные сети, deep learning, машинное обучение"
```

### Батч-обработка

Переменные автоматически передаются в BatchProcessor:

```python
from batch_processor import run_batch_processor
from src.variables_manager import VariablesManager

# Создать менеджер переменных
variables_manager = VariablesManager()
variables_manager.set_variables(
    author_style="technical",
    include_examples=True,
    article_length=5000
)

# Запустить батч с переменными
await run_batch_processor(
    topics_file="topics.txt",
    content_type="basic_articles",
    variables_manager=variables_manager
)
```

### Программное использование

```python
from src.variables_manager import VariablesManager

# Создание менеджера
vm = VariablesManager()

# Установка переменных
vm.set_variables(
    author_style="conversational",
    theme_focus="business applications",
    include_examples=True
)

# Получение аддонов для этапа
addon = vm.get_stage_addon("generate_article")
print(addon)
```

## Этапы пайплайна

### Соответствие функций и этапов

- `generate_article_by_sections` → `generate_article`
- `_generate_single_section_async` → `generate_article`
- `fact_check_sections` → `fact_check`
- `editorial_review` → `editorial_review`
- `create_structure` → `create_structure`

## Расширение системы

### Добавление новой переменной

1. Добавить определение в `variables_config.json`:

```json
{
  "variables": {
    "new_variable": {
      "type": "string",
      "default": null,
      "description": "Описание новой переменной",
      "stages": ["generate_article"],
      "prompt_addon": "🔧 НОВАЯ ИНСТРУКЦИЯ: {value}"
    }
  }
}
```

2. Добавить CLI аргумент в `main.py`:

```python
parser.add_argument('--new-variable', help='Описание новой переменной')
```

3. Обновить `create_from_args()` в `VariablesManager` если нужно.

### Поддержка новых типов данных

Система поддерживает string, number, boolean. Для добавления новых типов:

1. Обновить `_validate_type()` в `VariablesManager`
2. Обновить логику обработки в `get_stage_addon()`

## Совместимость

- ✅ Все типы контента (basic_articles, guides)
- ✅ Батч-обработка
- ✅ Обратная совместимость (переменные опциональны)
- ✅ Запуск с конкретных этапов (--start-from-stage)

## Логирование

Система логирует:
- Загрузку конфигурации переменных
- Установку активных переменных
- Применение аддонов к этапам

Уровни логирования:
- INFO: основные операции с переменными
- DEBUG: детальная информация о применении аддонов
- WARNING: проблемы с типами или неизвестные переменные

## Производительность

- Конфигурация загружается один раз при создании VariablesManager
- Аддоны генерируются динамически для каждого этапа
- Минимальный overhead при отсутствии активных переменных
- Поддержка очистки переменных между задачами в батч-режиме