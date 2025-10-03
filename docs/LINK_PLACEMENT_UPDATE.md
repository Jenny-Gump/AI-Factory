# Link Placement Feature - Stage 10

## Обновление нумерации этапов (октябрь 2025)

### Новая структура pipeline:
```
Этапы 1-9: Без изменений
Этап 10: Link Placement (НОВЫЙ) ← Расстановка ссылок
Этап 11: Editorial Review (было 10)
Этап 12: WordPress Publication (было 11)
```

### Что добавлено:

#### 1. Новая переменная
- **link_placement_mode**: on/off (по умолчанию on)
- Управление: `--link-placement-mode on/off`

#### 2. Функция place_links_in_sections()
- Расположение: `src/llm_processing.py`
- Группировка: по 3 секции (batch processing)
- Модель: deepseek/deepseek-chat-v3.1:free
- Fallback: google/gemini-2.5-flash-lite-preview-06-17

#### 3. Промпт
- Файл: `prompts/basic_articles/10_link_placement.txt`
- Количество ссылок: 4-7 на весь контент
- Формат: нативная интеграция в HTML
- Приоритет: официальные docs, GitHub, блоги компаний

#### 4. Поток данных
```
fact_checked_sections[] 
    ↓
place_links_in_sections() (Этап 10)
    ↓
content_with_links
    ↓
editorial_review() (Этап 11)
    ↓
wordpress_data_final
    ↓
WordPress Publication (Этап 12)
```

#### 5. Структура output папок
```
output/{topic}/
├── 09_fact_check/
├── 10_link_placement/        ← НОВАЯ ПАПКА
│   ├── group_1/
│   │   └── llm_responses_raw/
│   ├── link_placement_status.json
│   └── content_with_links.json
└── 11_editorial_review/      ← ПЕРЕИМЕНОВАНА (была 10_editorial_review)
```

#### 6. CLI команды
```bash
# Полный pipeline с link placement
python main.py "тема статьи"

# Отключить link placement
python main.py "тема" --link-placement-mode off

# Запустить только link placement
python main.py "тема" --start-from-stage link_placement
```

## Технические детали

### Retry система
- 3 попытки primary модели (DeepSeek)
- 3 попытки fallback модели (Gemini)
- Паузы 3 сек между группами

### Совместимость
- ✅ Работает с variables_manager
- ✅ Поддерживает все content_type
- ✅ Graceful fallback при ошибках
- ✅ Полное логирование в llm_responses_raw/

### Особенности промпта
- Нативная интеграция ссылок (НЕ отдельный список)
- Запрет на социальные сети и малоизвестные блоги
- Естественные анкорные тексты
- Равномерное распределение по секциям
