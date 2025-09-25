# LLM Response Formats Documentation

## Проблема решенная этим документом

**НИКОГДА БОЛЬШЕ НЕ ЧИНИТЬ ОДНО И ТО ЖЕ 10 РАЗ**

В функции `_parse_json_from_response` должна быть УМНАЯ логика определения правильного формата вместо тупого оборачивания всех объектов в массивы.

## Дефолтные форматы ответов по этапам

### 1. Ultimate Structure Creation (этап 7)
**Файл промпта**: `prompts/guides/02_create_ultimate_structure.txt`
**Ожидаемый формат**: ОБЪЕКТ
```json
{
    "article_structure": [
        {
            "section_title": "string",
            "section_order": number,
            "section_description": "string",
            "content_requirements": "string",
            "estimated_length": "string",
            "subsections": ["array"],
            "evidence_pack": "string"
        }
    ],
    "writing_guidelines": {
        "target_audience": "string",
        "tone_and_style": "string",
        "key_messaging": "string",
        "call_to_action": "string"
    }
}
```
**Обработка**: Возвращать КАК ЕСТЬ, НЕ оборачивать в массив!

### 2. Extract Prompts (этап 6)
**Ожидаемый формат**: МАССИВ структур
```json
[
    {
        "section_title": "string",
        "section_order": number,
        "content_requirements": "string",
        "subsections": ["array"],
        "evidence_pack": "string"
    }
]
```
**Обработка**: Возвращать как есть если массив, оборачивать если одиночный объект.

### 3. Editorial Review
**Ожидаемый формат**: ОБЪЕКТ с метаданными
```json
{
    "title": "string",
    "content": "HTML string",
    "excerpt": "string",
    "slug": "string",
    // ... другие мета-поля
}
```
**Обработка**: Возвращать как есть если имеет поля контента.

### 4. Link Processing
**Ожидаемый формат**: ОБЪЕКТ с планом ссылок
```json
{
    "link_plan": [
        {
            "anchor_text": "string",
            "query": "string",
            "section": "string",
            "ref_id": "string"
        }
    ]
}
```
**Обработка**: Извлекать `link_plan` массив.

## Логика в _parse_json_from_response

### SMART DETECTION RULES

1. **Если массив** → вернуть как есть
2. **Если объект с ключами `article_structure` + `writing_guidelines`** → Ultimate Structure → вернуть как есть
3. **Если объект с ключом `data`** → извлечь содержимое data
4. **Если объект с ключом `link_plan`** → извлечь содержимое link_plan
5. **Иначе одиночный объект структуры** → обернуть в массив для обратной совместимости

### Код в функции:
```python
if isinstance(parsed, dict):
    # Ultimate structure detection
    if "article_structure" in parsed and "writing_guidelines" in parsed:
        return parsed  # НЕ ОБОРАЧИВАЕМ!

    # Data wrapper detection
    elif "data" in parsed:
        return parsed["data"]

    # Link plan detection
    elif "link_plan" in parsed:
        return parsed["link_plan"]

    # Single structure - wrap for compatibility
    else:
        return [parsed]
```

## Тестовые случаи

### ✅ Правильная обработка Ultimate Structure
```json
INPUT:  {"article_structure": [...], "writing_guidelines": {...}}
OUTPUT: {"article_structure": [...], "writing_guidelines": {...}}  (БЕЗ оборачивания!)
```

### ✅ Правильная обработка массива структур
```json
INPUT:  [{"section_title": "..."}, {"section_title": "..."}]
OUTPUT: [{"section_title": "..."}, {"section_title": "..."}]  (Как есть)
```

### ✅ Правильная обработка одиночной структуры
```json
INPUT:  {"section_title": "..."}
OUTPUT: [{"section_title": "..."}]  (Обернуть в массив)
```

### ✅ Правильная обработка data wrapper
```json
INPUT:  {"data": [{"section_title": "..."}]}
OUTPUT: [{"section_title": "..."}]  (Извлечь data)
```

## При добавлении новых этапов

1. **Определить дефолтный формат** в промпте
2. **Добавить detection rule** в функцию парсинга если нужна особая логика
3. **Обновить этот документ** с новым форматом
4. **Протестировать** на реальных данных

## История изменений

- **2025-09-24**: Создан документ после исправления проблемы с двойным оборачиванием ultimate_structure
- Исправлена логика в `_parse_json_from_response` для корректного определения форматов