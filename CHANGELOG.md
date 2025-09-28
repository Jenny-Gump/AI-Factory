# Content Factory Changelog

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