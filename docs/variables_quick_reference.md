# Variables Quick Reference

## Маппинг переменных по стадиям и реальные тексты

### editorial_review
- `article_length` (number) - целевая длина статьи в символах
- `language` (string) - язык написания материала

**Реальные тексты отправляемые в LLM:**
```
⚠️ ВАЖНО: Пожалуйста, доведи статью до {value} символов без потери смысла, качества и важных моментов. Если статья короче - расширь важные разделы, добавь примеры. Если длиннее - сократи менее важные части.
🌍 ЯЗЫК: Пиши материал строго на {value} языке. Если встречаешь контент на ином языке, то переведи его.
```

### generate_article
- `author_style` (string) - стиль автора
- `theme_focus` (string) - фокус на тематике
- `target_audience` (string) - целевая аудитория
- `tone_of_voice` (string) - тон повествования
- `language` (string) - язык написания материала

**Реальные тексты отправляемые в LLM:**
```
📝 СТИЛЬ АВТОРА: Используй следующий стиль при написании: {value}
🎯 ФОКУС ТЕМЫ: Особое внимание удели следующей тематике: {value}
👥 ЦЕЛЕВАЯ АУДИТОРИЯ: Пиши для следующей аудитории: {value}
🎭 ТОН ПОВЕСТВОВАНИЯ: Используй следующий тон: {value}
🌍 ЯЗЫК: Пиши материал строго на {value} языке. Если встречаешь контент на ином языке, то переведи его.
```

### translation
- `language` (string) - целевой язык для перевода контента

**Логика работы:**
- ✅ Этап выполняется **ВСЕГДА** (обязательный этап пайплайна)
- `--language` указывает целевой язык перевода (по умолчанию "русский")
- Переменная `language` передается в функцию `translate_content()` как target_language
```

**Реальная логика в коде:**
```python
target_language = variables_manager.active_variables.get("language") or "русский"
# Translation выполняется ВСЕГДА с указанным языком
```

### create_structure
- `custom_requirements` (string) - дополнительные требования

**Реальный текст отправляемый в LLM:**
```
📋 ДОПОЛНИТЕЛЬНЫЕ ТРЕБОВАНИЯ: {value}
```

### Отключены (НЕ отправляются)
- `include_examples` (boolean) - включать примеры
- `seo_keywords` (string) - SEO ключевые слова

### Логические переменные (НЕ промпт-аддоны)

- `fact_check_mode` (string) - включить/отключить факт-чекинг ("on"/"off")
- `llm_model` (string) - override primary LLM model для этапов 8 и 12

**Поведение fact_check_mode:**
- `on` - обычный пайплайн с факт-чекингом
- `off` - пропуск факт-чекинга, статья идет сразу в редактор

**Поведение llm_model:**
- Заменяет **только** primary модель для этапов:
  - Этап 8 (generate_article) - генерация секций
  - Этап 12 (editorial_review) - редакторская обработка
- Fallback модели остаются **прежними** из конфига
- Примеры: "openai/gpt-5", "deepseek-reasoner", "openai/gpt-4o"

ПРИМЕР ОДНОЙ КОМАНДЫ СО ВСЕМИ ПЕРЕМЕННЫМИ:
```bash
python3 main.py "prompt injection how to be protected guide" \
  --content-type basic_articles \
  --author-style "technical" \
  --theme-focus "cybersecurity" \
  --target-audience "разработчики" \
  --tone-of-voice "professional" \
  --language "русский" \
  --custom-requirements "Больше примеров кода и реальных случаев" \
  --article-length 7000 \
  --fact-check-mode off \
  --llm-model "openai/gpt-5"
```