# Variables Quick Reference

## Маппинг переменных по стадиям и реальные тексты

### editorial_review
- `article_length` (number) - целевая длина статьи в символах

**Реальный текст отправляемый в LLM:**
```
⚠️ ВАЖНО: Пожалуйста, доведи статью до {value} символов без потери смысла, качества и важных моментов. Если статья короче - расширь важные разделы, добавь примеры. Если длиннее - сократи менее важные части.
```

### generate_article
- `author_style` (string) - стиль автора
- `theme_focus` (string) - фокус на тематике
- `target_audience` (string) - целевая аудитория
- `tone_of_voice` (string) - тон повествования

**Реальные тексты отправляемые в LLM:**
```
СТИЛЬ АВТОРА: Используй следующий стиль при написании: {value}
ФОКУС ТЕМЫ: Особое внимание удели следующей тематике: {value}
ЦЕЛЕВАЯ АУДИТОРИЯ: Пиши для следующей аудитории: {value}
ТОН ПОВЕСТВОВАНИЯ: Используй следующий тон: {value}
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



ПРИМЕР ОДНОЙ КОМАНДЫ СО ВСЕМИ ПЕРЕМЕННЫМИ:
```bash
python3 main.py "prompt injection how to be protected guide" \
  --content-type basic_articles \
  --author-style "technical" \
  --theme-focus "cybersecurity" \
  --target-audience "разработчики" \
  --tone-of-voice "professional" \
  --custom-requirements "Больше примеров кода и реальных случаев" \
  --article-length 7000
```