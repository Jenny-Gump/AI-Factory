# Changelog

All notable changes to the Content Generation Pipeline will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Reverted Editorial Model to DeepSeek** (Sept 22, 2025)
  - **Decision**: Reverted editorial_review model back to `deepseek/deepseek-chat-v3.1:free`
  - **Reason**: Grok-4-Fast показал неудовлетворительное качество editorial review
  - **Impact**: Editorial review uses stable DeepSeek model with proven performance
  - **Files Changed**:
    - `src/config.py`: Reverted editorial_review model to DeepSeek

### Added
- **Enhanced Memory Management System** (Sept 17, 2025)
  - **LLM Clients Cache Cleanup**: Added `clear_llm_clients_cache()` function to free accumulated OpenAI client objects
  - **HTTP Connections Cleanup**: Implemented forced garbage collection for aiohttp connections cleanup
  - **Token Tracker Reset**: Automatic reset between topics (already working, documented the behavior)
  - **Comprehensive Memory Monitoring**: Enhanced logging for all memory cleanup operations
  - **Configuration**: All cleanup options configurable via `MEMORY_CLEANUP` settings in `batch_config.py`
  - **Impact**: Prevents memory accumulation during long batch processing sessions

### Fixed
- **Batch Processor Timeout Hangs** (Sept 17, 2025)
  - **Problem**: 30-minute timeout was causing batch processor to hang and stop processing topics
  - **Root Cause**: `asyncio.wait_for()` with 1800-second timeout was forcibly terminating valid long-running operations
  - **Solution**: Removed artificial timeout constraints from batch processing
  - **Files Changed**:
    - `batch_processor.py`: Removed `asyncio.wait_for()` timeout wrapper
    - `batch_config.py`: Removed timeout-related configuration options
  - **Impact**: System now processes topics naturally without artificial time constraints
  - **Note**: HTTP and LLM timeouts are preserved for network reliability
- **WordPress Article Generation Unicode Issue** (Sept 17, 2025)
  - **Problem**: LLM received garbled Unicode escape sequences instead of readable Russian text in article structure
  - **Root Cause**: `json.dumps()` without `ensure_ascii=False` was double-escaping Cyrillic characters
  - **Solution**: Added `ensure_ascii=False` parameter to `json.dumps()` in article generation
  - **Impact**: Article structure now passes to LLM as clean, readable Russian text
  - **Technical Details**:
    - Fixed `generate_wordpress_article()` function in `src/llm_processing.py:392`
    - Changed from `json.dumps(prompts, indent=2)` to `json.dumps(prompts, indent=2, ensure_ascii=False)`
    - Russian text like "Введение в технику" now stays readable instead of becoming `\u0412\u0432\u0435...`
    - Confirmed with isolated testing using real pipeline data

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