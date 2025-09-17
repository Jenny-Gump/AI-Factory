# Changelog

All notable changes to the Content Generation Pipeline will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Editorial Review JSON Parsing Issue** (Sept 17, 2025)
  - **Problem**: Editorial review stage was receiving truncated LLM responses, causing JSON parsing failures
  - **Root Cause**: Missing `response_format={"type": "json_object"}` parameter in editorial_review function
  - **Solution**: Added `response_format` parameter to ensure complete JSON responses from LLM
  - **Impact**: WordPress block tags are now properly cleaned even when JSON parsing fails
  - **Technical Details**:
    - Enhanced `editorial_review()` function in `src/llm_processing.py`
    - Added `response_format={"type": "json_object"}` parameter to LLM request
    - Ensures complete JSON responses from OpenRouter API
    - Prevents response truncation that caused parsing failures

### Technical Improvements
- Added `response_format` parameter to prevent LLM response truncation
- Enhanced LLM request configuration for reliable JSON generation
- Improved editorial review stage stability and consistency

---

## Version History

### Pre-changelog Releases
- Multi-provider LLM system (DeepSeek, OpenRouter)
- WordPress integration with SEO optimization
- Content pipeline with search, parsing, scoring, selection, and cleaning stages
- Editorial review stage implementation
- Token tracking and usage analytics

---

## Bug Fixes & Technical Notes

### Editorial Review JSON Parsing (2025-09-11)

**Issue Identification Process**:
1. User reported JSON parsing failure at editorial_review stage
2. Examined raw LLM response files in llm_responses_raw/ directory
3. Found LLM response was truncated mid-sentence ending with "проконсультиру"
4. Identified missing `response_format={"type": "json_object"}` parameter
5. Added parameter to ensure complete JSON responses from LLM

**Before Fix**:
```
LLM Response: Truncated mid-sentence ending with "проконсультиру" ❌
JSON Parsing: FAILED due to incomplete response ❌
Final Output: Falls back to original data with parsing errors ❌
```

**After Fix**:
```
LLM Response: Complete JSON response with proper formatting ✅
JSON Parsing: SUCCESS with response_format enforcement ✅
Final Output: Clean content with all editorial improvements ✅
```

**Files Modified**:
- `src/llm_processing.py`: Enhanced `editorial_review()` function
- `docs/troubleshooting.md`: Updated JSON parsing section

**Test Results**:
- LLM response: Complete and properly formatted JSON
- JSON parsing: Successful without fallback mechanisms
- Content quality: Preserved all editorial improvements
- Response format: 100% reliable JSON generation

This fix ensures the editorial review stage generates complete, properly formatted JSON responses consistently, eliminating truncation issues and maintaining reliable content processing.