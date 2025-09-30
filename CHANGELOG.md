# Content Factory Changelog

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