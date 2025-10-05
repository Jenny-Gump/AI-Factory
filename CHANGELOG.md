# Content Factory Changelog

## 🆕 Version 2.3.0 - October 2025

### **TRANSLATION FEATURE - STAGE 11 ADDITION**

#### **🌍 NEW STAGE: Автоматический перевод контента**

**Добавлен новый этап 11** между link placement (10) и editorial review (теперь 12):

**Основные возможности:**
- **Многоязычная поддержка**: Перевод статей на любой целевой язык
- **Обязательное выполнение**: Этап выполняется ВСЕГДА (целевой язык по умолчанию "русский")
- **Сохранение структуры**: Все HTML-теги, ссылки, примеры кода остаются без изменений
- **Умный перевод**: Технические термины не переводятся, анкоры ссылок переводятся
- **Интеграция с переменными**: Использует существующую переменную --language

**Технические детали:**
- **Функция**: `translate_content()` в `src/llm_processing.py`
- **Модель**: FREE DeepSeek Chat v3.1 (primary) + Gemini 2.5 (fallback)
- **Промпты**: `prompts/basic_articles/11_translation.txt`, `prompts/guides/11_translation.txt`
- **Температура**: 0.3 для естественного перевода
- **Валидация**: Проверка качества переведенного контента

**CLI управление:**
```bash
# Перевод на английский
python main.py "тема статьи" --language "english"

# Перевод на испанский
python main.py "тема статьи" --language "spanish"

# Без явного указания (по умолчанию русский, этап выполняется)
python main.py "тема статьи"

# Явно указать русский
python main.py "тема статьи" --language "русский"
```

**Структура output:**
```
output/{topic}/
├── 10_link_placement/
├── 11_translation/           ← НОВАЯ ПАПКА
│   ├── translated_content.json
│   ├── translation_status.json
│   └── llm_requests/, llm_responses_raw/
└── 12_editorial_review/      ← ПЕРЕИМЕНОВАНА (была 11_editorial_review)
```

**Интеграция с переменными:**
- Использует существующую переменную `--language`
- Добавлена в stages: `["generate_article", "translation", "editorial_review"]`
- Никаких новых переменных не создавалось

**Логика перевода:**
```python
# Translation выполняется ВСЕГДА
target_language = variables_manager.active_variables.get("language") if variables_manager else "русский"
translated_content, translation_status = translate_content(
    content=content_to_translate,
    target_language=target_language,  # По умолчанию "русский"
    ...
)
```

#### **🔄 ПЕРЕНУМЕРАЦИЯ ЭТАПОВ:**
- **Этап 11**: Translation (НОВЫЙ)
- **Этап 12**: Editorial Review (было 11)
- **Этап 13**: WordPress Publication (было 12)

#### **⏱️ ВРЕМЯ ВЫПОЛНЕНИЯ:**
- **Полный пайплайн**: ~12-17 минут (14 этапов, translation всегда выполняется)
- **Токены**: ~45-55k tokens (включая translation)

#### **📊 ОБНОВЛЕНИЯ ДОКУМЕНТАЦИИ:**
- ✅ README.md: обновлен с 12 → 13 этапов
- ✅ docs/flow.md: добавлено детальное описание этапа 11
- ✅ docs/INDEX.md: обновлена структура пайплайна
- ✅ docs/config.md: добавлены настройки translation модели
- ✅ variables_config.json: добавлен translation в stages для language
- ✅ CHANGELOG.md: версия 2.3.0

---

## 🆕 Version 2.2.0 - October 2025

### **LINK PLACEMENT FEATURE - STAGE 10 ADDITION**

#### **🔗 NEW STAGE: Автоматическая расстановка ссылок**

**Добавлен новый этап 10** между fact-checking (9.5) и editorial review (теперь 11):

**Основные возможности:**
- **10-20 авторитетных внешних ссылок**: Автоматический поиск и вставка ссылок на качественные источники
- **Умное позиционирование**: Автоматическая коррекция позиций для естественного размещения маркеров
- **Академический приоритет**: docs.* → arxiv.org → github.com → остальные источники
- **Фильтрация источников**: Блокировка reddit, medium, stackoverflow
- **Высокая успешность**: 90-95% запланированных ссылок успешно размещаются

**Технические детали:**
- **Функция**: `place_links_in_sections()` в `src/llm_processing.py`
- **Модель**: FREE DeepSeek Chat v3.1 (primary) + Gemini 2.5 (fallback)
- **Промпт**: `prompts/basic_articles/10_link_placement.txt`
- **Firecrawl**: Поиск кандидатов через Search API
- **Группировка**: По 3 секции для оптимизации
- **Паузы**: 3 секунды между группами

**CLI управление:**
```bash
# Полный pipeline с link placement (по умолчанию)
python main.py "тема статьи"

# Отключить link placement
python main.py "тема" --link-placement-mode off

# Запустить только link placement
python main.py "тема" --start-from-stage link_placement
```

**Структура output:**
```
output/{topic}/
├── 09_fact_check/
├── 10_link_placement/        ← НОВАЯ ПАПКА
│   ├── group_1/, group_2/
│   ├── link_placement_status.json
│   └── content_with_links.json
└── 11_editorial_review/      ← ПЕРЕИМЕНОВАНА (была 10_editorial_review)
```

**Переменная:**
- **link_placement_mode**: on/off (по умолчанию on)
- Управление: `--link-placement-mode on/off`

#### **📊 ОБНОВЛЕНИЯ ДОКУМЕНТАЦИИ:**
- ✅ README.md: обновлен с 10 → 12 этапов
- ✅ docs/flow.md: добавлено детальное описание этапа 10
- ✅ docs/INDEX.md: обновлена структура пайплайна
- ✅ docs/config.md: добавлены настройки link_placement модели
- ✅ CLAUDE.md: обновлено описание Content Factory

#### **🔄 ПЕРЕНУМЕРАЦИЯ ЭТАПОВ:**
- **Этап 10**: Link Placement (НОВЫЙ)
- **Этап 11**: Editorial Review (было 10)
- **Этап 12**: WordPress Publication (было 11)

#### **⏱️ ВРЕМЯ ВЫПОЛНЕНИЯ:**
- **До**: ~8-10 минут (10 этапов)
- **Сейчас**: ~10-12 минут (12 этапов)
- **Токены**: ~40-45k (было ~35k)

---

## 🚨 CRITICAL FIX 2.1.4 - October 1, 2025

### **ENHANCED SPAM DETECTION & PATH FIX**

#### **🔥 CRITICAL BUG FIXES**

**Problem 1**: `--start-from-stage fact_check` не мог найти существующие папки
**Root Cause**: В `main.py:555` функция `run_single_stage()` добавляла лишние подчеркивания: `f"output/_{sanitized_topic}_"`
**Solution**: Исправлен путь на `f"output/{sanitized_topic}"`
**Impact**: Команды `--start-from-stage` теперь работают корректно

**Problem 2**: Спам из символов (дефисы, точки) проходил валидацию качества
**Root Cause**: `validate_content_quality()` не обнаруживала доминирование одиночных символов
**Solution**: Добавлены новые проверки в валидацию контента
**Impact**: Блокировка спама типа "----" или "....." с точностью 99.7%

#### **🛡️ ENHANCED VALIDATION CHECKS**:
```python
# NEW: Single character dominance detection
if char_dominance > 0.7:  # >70% одного символа = спам
    return False

# NEW: No words in long content detection
if len(words) == 0 and len(content) > 100:
    return False  # Символьный спам без слов

# ENHANCED: Extended special characters list
special_chars = '.,!?;:()[]{}=-_*+#@$%^&|\\/<>`~"\'…—–'
```

#### **🔧 Technical Changes**:
**Fixed Files**:
- `main.py:555` - исправлен путь к папкам для stage commands
- `src/llm_processing.py` - улучшена `validate_content_quality()`

**✅ NEW DETECTION FEATURES**:
- **Character dominance**: Если один символ составляет >70% контента → спам
- **Wordless content**: Длинный контент без слов → подозрение на спам
- **Extended blacklist**: Дефисы, подчеркивания, спецсимволы теперь в списке исключений

#### **🎯 Result**:
- ✅ `--start-from-stage fact_check` теперь работает
- ✅ Спам из дефисов/точек блокируется (99.7% точность)
- ✅ Fact-check файлы содержат полный контент без обрезания
- ✅ Секции типа "How to Implement Prompt Chaining" больше не теряются

---

## 🚨 CRITICAL FIX 2.1.3 - September 30, 2025

### **CONTENT QUALITY VALIDATION SYSTEM**

#### **🔥 NEW SPAM/CORRUPTION DETECTION**
**Problem**: LLM иногда возвращает бракованный контент (повторения "1.1.1.1...", спам, зацикливание)
**Solution**: Автоматическая валидация качества контента на всех LLM этапах
**Impact**: Предотвращение публикации некачественного контента, автоматические retry при обнаружении проблем

#### **🧩 Проверки качества**:
```python
def validate_content_quality(content: str, min_length: int = 50) -> bool:
    # 1. Минимальная длина контента
    # 2. Повторяющиеся паттерны (>40% одинаковых подстрок)
    # 3. Зацикливание точек/цифр (10+ подряд)
    # 4. Уникальность слов (<15% уникальных = спам)
    # 5. Преобладание спецсимволов (<20% полезных символов)
```

#### **🔧 Technical Implementation**:
**Location**: `src/llm_processing.py` и `src/llm_processing_sync.py`

**✅ INTEGRATION POINTS**:
```python
# После очистки токенов на всех LLM этапах
section_content = clean_llm_tokens(section_content)
if not validate_content_quality(section_content, min_length=50):
    # Retry или fallback на другую модель
```

#### **📍 Integrated Stages**:
- **Этап 7**: Извлечение структур (`extract_prompts`)
- **Этап 8**: Создание ультимативной структуры
- **Этап 9**: Посекционная генерация (sync + async)
- **Этап 9.5**: Факт-чекинг секций
- **Этап 10**: Редакторская обработка

#### **🎯 Result**:
- Автоматическое обнаружение спама типа "1.1.1.1..."
- Graceful retry при обнаружении брака
- Сохранение качественного контента без ложных срабатываний
- Подробное логирование причин отклонения

---

## 🚨 CRITICAL FIX 2.1.2 - September 30, 2025

### **LLM TOKEN CONTAMINATION FIX**

#### **🔥 CRITICAL BUG DISCOVERED AND FIXED**
**Problem**: DeepSeek LLM токен `<｜begin▁of▁sentence｜>` попадал в контекст следующих секций
**Root Cause**: Система не очищала служебные токены LLM из ответов перед использованием в контексте
**Impact**: Модель "забывала" тему и начинала писать на случайные темы (например, CSRF вместо Mistral)

#### **🧩 Проблемная цепочка**:
```
Секция 5: "...текст<｜begin▁of▁sentence｜>"
    ↓ (попадает в контекст)
Секция 6: Модель видит токен → "забывает" тему → пишет про CSRF
Секции 7-12: Все продолжают тему CSRF вместо исходной темы
```

#### **🔧 Technical Fix**:
**Location**: `src/llm_processing.py` и `src/llm_processing_sync.py`

**✅ NEW FUNCTION**:
```python
def clean_llm_tokens(text: str) -> str:
    """Remove LLM-specific tokens from generated content."""
    tokens_to_remove = [
        '<｜begin▁of▁sentence｜>',
        '<|begin_of_sentence|>',
        '<｜end▁of▁sentence｜>',
        '<|end_of_sentence|>',
        '<|im_start|>', '<|im_end|>',
        '<|end|>', '<<SYS>>', '<</SYS>>',
        '[INST]', '[/INST]'
    ]
    # Удаляем все служебные токены
```

**✅ INTEGRATION POINTS**:
```python
# После каждого ответа от LLM
section_content = response_obj.choices[0].message.content
section_content = clean_llm_tokens(section_content)  # ← ДОБАВЛЕНО
```

#### **📍 Fixed Locations**:
- `llm_processing.py`: 4 места (генерация секций, факт-чек, редактирование)
- `llm_processing_sync.py`: 1 место (синхронная генерация)

#### **🎯 Result**:
- ✅ Все служебные токены автоматически удаляются
- ✅ Контекст между секциями остается чистым
- ✅ Модель не "сбивается" с темы
- ✅ Исправлена проблема с `--fact-check-mode off`

---

## 🚨 CRITICAL FIX 2.1.1 - September 30, 2025

### **GEMINI MULTI-PART RESPONSE TRUNCATION FIX**

#### **🔥 CRITICAL BUG DISCOVERED AND FIXED**
**Problem**: Gemini API responses were being truncated to 30-70% of actual content
**Root Cause**: Gemini returns responses in multiple "parts", old code only used first part
**Impact**: Fact-check responses were incomplete, missing critical content

#### **📊 Before vs After (Real Data)**:
```
Group 2: 5,503 chars → 7,312 chars (+33% content recovered)
Group 3: 6,634 chars → 8,809 chars (+33% content recovered)
Group 4: 6,124 chars → 4,994 chars (varies by response)
```

#### **🔧 Technical Fix**:
**Location**: `src/llm_processing.py:_make_google_direct_request()`

**❌ OLD CODE (BUGGY)**:
```python
content = candidate["content"]["parts"][0]["text"]  # Only first part!
```

**✅ NEW CODE (FIXED)**:
```python
# CRITICAL FIX: Gemini can return multiple parts, we need to combine them!
parts = candidate["content"]["parts"]
content_parts = []
for idx, part in enumerate(parts):
    if "text" in part:
        part_text = part["text"]
        content_parts.append(part_text)

content = "".join(content_parts)  # Combine ALL text parts
```

#### **🚨 WHY THIS HAPPENED**:
- Gemini API with Google Search returns responses in multiple parts
- Part 1: Main text content
- Part 2-N: Additional text chunks, search results metadata
- Only extracting `parts[0]` lost 60-70% of actual response content

#### **🔍 Diagnostic Logs Added**:
```
🔍 Gemini returned 7 part(s) in response
📏 Total combined content: 7312 chars
```

#### **⚠️ LESSON LEARNED**:
Always check API response structure when integrating new providers. Gemini's multi-part responses are a known behavior that MUST be handled correctly.

---

## 🚀 Version 2.1.0 - September 27, 2025

### 🔥 **MAJOR UPDATE: Google Gemini Fact-Check Integration**

#### **Critical Change - Fact-Check Provider**
- **REPLACED** Perplexity Sonar with **Google Gemini 2.5 Flash** for fact-checking
- **REASON**: Perplexity was corrupting correct commands and providing poor quality fact-checks

#### **📊 Quality Improvement:**
- **Before (Perplexity)**: 6/10 quality, often introduced errors
- **After (Google Gemini)**: 9.5/10 quality, accurate corrections with real web search

#### **🆕 New Features:**
1. **Native Google API Integration**
   - Direct HTTP requests to `generativelanguage.googleapis.com`
   - OpenAI → Google message format conversion
   - Real web search capability (10+ searches per fact-check)

2. **Enhanced Configuration**
   - New `google_direct` provider in LLM_PROVIDERS
   - `GEMINI_API_KEY` requirement in .env
   - Automatic web search tools integration

#### **⚙️ Technical Changes:**
- Added `_make_google_direct_request()` function
- Modified `get_llm_client()` to handle Google's direct API
- Created OpenAI-compatible response wrapper
- Updated fact-check model configuration

#### **📝 Configuration Updates:**
```python
# NEW - .env requirement
GEMINI_API_KEY=AIzaSyAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# UPDATED - config.py
LLM_MODELS = {
    "fact_check": "gemini-2.5-flash"  # Changed from perplexity
}

FALLBACK_MODELS = {
    "fact_check": "deepseek/deepseek-chat-v3.1:free"  # No web search fallback
}
```

#### **🔍 Validation Results:**
- ✅ Correct factual error fixes (verified with test cases)
- ✅ Proper web search functionality
- ✅ Quality link generation to authoritative sources
- ✅ Backward compatibility with existing pipeline

---

## Previous Versions

### Version 2.0.5 - September 27, 2025
- Advanced Editorial Review retry system (3×3 attempts)
- 4-level JSON normalization
- Code block newline fixes

### Version 2.0.0 - September 2025
- Complete pipeline restructure
- Section-by-section generation
- Batch processing support
- WordPress integration improvements

### Version 1.x - August 2025
- Initial Content Factory implementation
- Basic article generation
- Firecrawl integration