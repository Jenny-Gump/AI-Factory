# WordPress Integration

Content Factory автоматически публикует статьи на https://ailynx.ru в категории "prompts" в статусе черновика с полной поддержкой Yoast SEO через Custom Post Meta Endpoint.

## Настройка и тестирование

### Создание категории "prompts" (одноразово)
```bash
python3 create_prompts_category.py
```

### Автоматический тест публикации
```bash  
python3 test_publication_auto.py
```

### Результат успешного теста
```
INTEGRATION TEST PASSED!
WordPress ID: 4377
Edit URL: https://ailynx.ru/wp-admin/post.php?post=4377&action=edit
```

## Использование

```bash
# Генерация + автоматическая публикация (по умолчанию)
python3 main.py "Промпты для анализа данных"

# Без публикации (только для batch_processor.py)
python3 batch_processor.py topics.txt --skip-publication

# С кастомными моделями (только batch_processor.py)
python3 batch_processor.py topics.txt --generate-model openai/gpt-4o
```

## Технические детали

### WordPress настройки
- **Сайт**: https://ailynx.ru
- **Аккаунт**: PetrovA (основной аккаунт)
- **Категория**: "prompts" (ID: 825)
- **Статус**: draft (для безопасности)
- **Кодировка**: UTF-8, русский язык
- **Публикация**: Автоматическая по умолчанию в main.py

### Custom Post Meta Endpoint
- **Эндпоинт**: `https://ailynx.ru/wp-json/custom-post-meta/v1/posts/`
- **API ключ**: Проверить актуальность в config.py
- **Статус**: Проверить настройки в конфигурации
- **Назначение**: Обходит ограничения WordPress REST API для записи Yoast мета-полей

### Yoast SEO поля (автоматически заполняются)
- `_yoast_wpseo_title`: SEO заголовок (до 60 символов)
- `_yoast_wpseo_metadesc`: Мета-описание (до 160 символов)
- `_yoast_wpseo_focuskw`: Ключевое слово

### Структура публикации
```json
{
  "title": "Заголовок статьи",
  "content": "<h2>HTML контент</h2>",
  "status": "draft",
  "categories": [825],
  "meta": {
    "_yoast_wpseo_title": "SEO заголовок",
    "_yoast_wpseo_metadesc": "SEO описание"
  }
}
```

---

**Статус**: Готово к использованию | **Протестировано**: WordPress ID 4377