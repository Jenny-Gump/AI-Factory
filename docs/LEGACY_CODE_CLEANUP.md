# 🧹 Legacy Code Cleanup Guide

## 📋 Обзор проблемы

Проект содержит значительное количество legacy кода от старой архитектуры с множественными типами контента. **В настоящее время работает только пайплайн `basic_articles`**, остальные компоненты являются нефункциональными заглушками.

---

## 🔍 Детальный анализ Legacy кода

### 1. **КРИТИЧЕСКАЯ ПРОБЛЕМА: Неработающие типы контента**

#### 📁 `batch_config.py` - Фиктивные конфигурации
```python
CONTENT_TYPES = {
    "prompt_collection": {        # ❌ НЕ РАБОТАЕТ - нет функции pipeline
        "prompts_folder": "prompts/prompt_collection",
        "description": "Articles about AI prompts and prompt engineering",
        "default_topics_file": "topics_prompts.txt",
        "output_prefix": "prompts_",
        "wordpress_category": "prompts"
    },
    "business_ideas": {           # ❌ НЕ РАБОТАЕТ - нет папки, нет pipeline
        "prompts_folder": "prompts/business_ideas",
        "description": "Business ideas and entrepreneurship content",
        "default_topics_file": "topics_business_ideas.txt",
        "output_prefix": "business_",
        "wordpress_category": "business"
    },
    "marketing_content": {        # ❌ НЕ РАБОТАЕТ - нет папки, нет pipeline
        "prompts_folder": "prompts/marketing_content",
        "description": "Marketing and advertising content",
        "default_topics_file": "topics_marketing.txt",
        "output_prefix": "marketing_",
        "wordpress_category": "marketing"
    },
    "educational_content": {      # ❌ НЕ РАБОТАЕТ - нет папки, нет pipeline
        "prompts_folder": "prompts/educational_content",
        "description": "Educational and tutorial content",
        "default_topics_file": "topics_educational.txt",
        "output_prefix": "edu_",
        "wordpress_category": "education"
    },
    "basic_articles": {           # ✅ ЕДИНСТВЕННЫЙ РАБОЧИЙ
        "prompts_folder": "prompts/basic_articles",
        "description": "Basic informational articles with FAQ and sources",
        "default_topics_file": "topics_basic_articles.txt",
        "output_prefix": "article_",
        "wordpress_category": "articles"
    }
}
```

**Проблема**: `batch_processor.py` по умолчанию использует `prompt_collection`, но этого пайплайна не существует!

### 2. **УСТАРЕВШАЯ ФУНКЦИЯ: `extract_prompts_from_article()`**

#### 📁 `src/llm_processing.py:431-485`
```python
def extract_prompts_from_article(article_text: str, topic: str, base_path: str = None,
                                 source_id: str = None, token_tracker: TokenTracker = None,
                                 model_name: str = None) -> List[Dict]:
    """Extracts structured prompt data from a single article text."""
    # ❌ ПРОБЛЕМА: Вызывается в main.py но не соответствует basic_articles пайплайну
    messages = _load_and_prepare_messages(
        "basic_articles",  # Пытается загрузить basic_articles промпты
        "01_extract",      # Но логика функции для prompt_collection
        {"topic": topic, "article_text": article_text}
    )
```

**Вызывается в**: `main.py:139` - но логика не соответствует текущему пайплайну

### 3. **МЕРТВЫЕ ФАЙЛЫ И ПАПКИ**

#### 📁 Фиктивные промпты
```
prompts/prompt_collection/
├── 01_extract.txt                    # ❌ Заглушка с TODO
└── 01_generate_wordpress_article.txt # ❌ Заглушка с TODO
```

Содержимое файлов:
```
# Placeholder for prompt_collection extraction prompts
# TODO: Add specific prompts for this content type
```

#### 📁 Временные batch файлы
```
.batch_progress_prompt_collection.json  # ❌ Старый прогресс файл
.batch_lock_prompt_collection.pid       # ❌ Lock файл
```

### 4. **ДОКУМЕНТАЦИЯ С НЕРАБОТАЮЩИМИ ПРИМЕРАМИ**

#### 📁 `README.md` - Описание несуществующих функций
```markdown
- 📝 **Коллекции промптов** (`prompt_collection`) - классический 8-этапный пайплайн
```

#### 📁 `docs/flow.md` - Ссылки на несуществующие промпты
```markdown
- Промпт-шаблон `prompts/prompt_collection/01_generate_wordpress_article.txt`
- Промпт-шаблон `prompts/prompt_collection/02_editorial_review.txt`
```

#### 📁 `docs/link_processing.md` - Неработающие команды
```bash
python3 batch_processor.py topics_file.txt --content-type prompt_collection
```

### 5. **АРХИТЕКТУРНЫЙ КОНФЛИКТ**

#### 📁 `batch_processor.py` - Неправильные дефолты
```python
def __init__(self, topics_file: str, content_type: str = "prompt_collection",  # ❌ НЕ РАБОТАЕТ
             model_overrides: Dict = None, resume: bool = False,
             skip_publication: bool = False):

async def run_batch_processor(topics_file: str, content_type: str = "prompt_collection",  # ❌ НЕ РАБОТАЕТ

parser.add_argument("--content-type", default="prompt_collection",  # ❌ НЕ РАБОТАЕТ
```

**Результат**: Batch processor ломается при запуске без флагов.

---

## 🎯 План поэтапной очистки

### **ЭТАП 1: Критические исправления (БЕЗОПАСНО)**

#### 1.1 Исправить дефолты в `batch_processor.py`
```python
# БЫЛО:
content_type: str = "prompt_collection"

# ДОЛЖНО БЫТЬ:
content_type: str = "basic_articles"
```

#### 1.2 Удалить мертвые batch файлы
```bash
rm .batch_progress_prompt_collection.json
rm .batch_lock_prompt_collection.pid
```

### **ЭТАП 2: Очистка конфигурации (БЕЗОПАСНО)**

#### 2.1 Удалить неработающие типы из `batch_config.py`
Оставить только:
```python
CONTENT_TYPES = {
    "basic_articles": {
        "prompts_folder": "prompts/basic_articles",
        "description": "Basic informational articles with FAQ and sources",
        "default_topics_file": "topics_basic_articles.txt",
        "output_prefix": "article_",
        "wordpress_category": "articles"
    }
}
```

#### 2.2 Удалить папку `prompts/prompt_collection/`
```bash
rm -rf prompts/prompt_collection/
```

### **ЭТАП 3: Код и функции (ТРЕБУЕТ АНАЛИЗА)**

#### 3.1 Анализ функции `extract_prompts_from_article()`
**ВОПРОС**: Используется ли эта функция в текущем `basic_articles` пайплайне?

- Если НЕТ → удалить полностью
- Если ДА → переписать под `basic_articles` логику

#### 3.2 Проверка импортов в `main.py`
```python
from src.llm_processing import (
    extract_prompts_from_article,  # ❓ Нужна ли?
    # extract_prompts_from_article_async,  # REMOVED: уже помечена как REMOVED
```

### **ЭТАП 4: Документация (БЕЗОПАСНО)**

#### 4.1 Обновить `README.md`
- Удалить упоминания `prompt_collection`
- Оставить только описание `basic_articles`

#### 4.2 Обновить `docs/flow.md`
- Удалить неработающие примеры
- Исправить пути к промптам

#### 4.3 Обновить `docs/link_processing.md`
- Исправить команды запуска batch processor

---

## ⚠️ Риски и предосторожности

### **ВЫСОКИЙ РИСК**
- `extract_prompts_from_article()` - неясно используется ли в `basic_articles`

### **СРЕДНИЙ РИСК**
- Изменение дефолтов в `batch_processor.py` - может повлиять на существующие скрипты

### **НИЗКИЙ РИСК**
- Удаление мертвых файлов и папок
- Очистка конфигурации неработающих типов
- Обновление документации

---

## 🧪 План тестирования после очистки

### 1. Функциональные тесты
```bash
# Тест основного пайплайна
python main.py "Test topic"

# Тест batch процессора БЕЗ флагов (должен работать с basic_articles)
python batch_processor.py topics_basic_articles.txt

# Тест batch процессора С флагом
python batch_processor.py topics_basic_articles.txt --content-type basic_articles
```

### 2. Проверка импортов
```bash
python -c "from main import *; print('Imports OK')"
python -c "from batch_processor import *; print('Batch imports OK')"
```

### 3. Проверка документации
- Все команды в README.md должны работать
- Все ссылки на файлы должны существовать

---

## 📊 Ожидаемые результаты

### **Перед очисткой:**
- ❌ `python batch_processor.py topics.txt` - ломается
- ❌ 4 фиктивных типа контента в конфиге
- ❌ Мертвые файлы и папки
- ❌ Неточная документация

### **После очистки:**
- ✅ `python batch_processor.py topics.txt` - работает
- ✅ 1 рабочий тип контента (`basic_articles`)
- ✅ Чистая файловая структура
- ✅ Точная документация

---

## 📝 Чек-лист выполнения

### Этап 1: Критические исправления
- [ ] Изменить дефолт в `BatchProcessor.__init__()`
- [ ] Изменить дефолт в `run_batch_processor()`
- [ ] Изменить дефолт в `parser.add_argument()`
- [ ] Удалить `.batch_progress_prompt_collection.json`
- [ ] Удалить `.batch_lock_prompt_collection.pid`
- [ ] Протестировать `python batch_processor.py topics_basic_articles.txt`

### Этап 2: Очистка конфигурации
- [ ] Удалить неработающие типы из `CONTENT_TYPES`
- [ ] Удалить папку `prompts/prompt_collection/`
- [ ] Протестировать конфигурацию

### Этап 3: Анализ кода
- [ ] Проанализировать использование `extract_prompts_from_article()`
- [ ] Принять решение: удалить или переписать
- [ ] Очистить неиспользуемые импорты

### Этап 4: Документация
- [ ] Обновить `README.md`
- [ ] Обновить `docs/flow.md`
- [ ] Обновить `docs/link_processing.md`
- [ ] Проверить все команды в документации

---

**Дата создания**: 20 сентября 2025
**Статус**: План готов к выполнению
**Приоритет**: ВЫСОКИЙ (блокирует нормальную работу batch processor)