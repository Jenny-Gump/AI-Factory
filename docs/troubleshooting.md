# Troubleshooting & Debugging Guide

This guide covers troubleshooting, debugging, and optimization for the Basic Articles pipeline.

## 📋 Quick Navigation

1. [LLM Debugging](#llm-debugging) - Debug LLM interactions and responses
2. [JSON Parsing Issues](#json-parsing-issues) - Fix common parsing problems
3. [Performance Optimization](#performance-optimization) - Speed up the pipeline
4. [Content Quality Issues](#content-quality-issues) - Improve output quality
5. [Configuration Problems](#configuration-problems) - Fix setup issues

---

## 🔍 LLM Debugging

Every LLM interaction is automatically logged with full transparency for debugging.

### Directory Structure

When you run the pipeline, detailed logs are saved:

```
output/Your_Topic/
├── token_usage_report.json          # Token usage analytics
├── 06_structure_extraction/         # Stage: Extract structures
│   ├── all_structures.json         # Final processed results
│   ├── llm_requests/                # What was sent to LLM
│   │   ├── source_1_request.json   # Full request with model info
│   │   └── source_2_request.json
│   └── llm_responses_raw/           # Raw LLM responses
│       ├── source_1_response.txt   # Unprocessed LLM output
│       └── source_2_response.txt
├── 07_ultimate_structure/
│   ├── ultimate_structure.json
│   ├── llm_requests/
│   └── llm_responses_raw/
├── 08_article_generation/
│   ├── wordpress_data.json
│   ├── llm_requests/
│   └── llm_responses_raw/
└── 09_editorial_review/
    ├── wordpress_data_final.json
    ├── llm_requests/
    └── llm_responses_raw/
```

### Debugging Workflow

**1. Start with raw LLM data:**
- Check `llm_responses_raw/*.txt` files first
- See exactly what the LLM returned
- Don't rely on logs or processed JSON

**2. Follow the data chain:**
- Input → LLM → Raw response → Parsed JSON → Final output
- Find where data changes unexpectedly

**3. Check prompts:**
- Look at `llm_requests/*.json` files
- Verify prompt content and parameters
- Check if instructions are clear

**4. Common debugging steps:**
```bash
# Check raw responses for a specific stage
cat output/Your_Topic/06_structure_extraction/llm_responses_raw/source_1_response.txt

# Check what was sent to LLM
cat output/Your_Topic/06_structure_extraction/llm_requests/source_1_request.json

# Check final processed results
cat output/Your_Topic/06_structure_extraction/all_structures.json
```

---

## ⚠️ JSON Parsing Issues

### Symptom: "JSON parsing failed" errors

**Common causes:**
1. LLM returned invalid JSON format
2. Escaped characters in content
3. Incomplete JSON response

**Debug process:**
1. Check raw response file: `llm_responses_raw/*.txt`
2. Look for malformed JSON:
   - Missing closing braces `}`
   - Unescaped quotes inside strings
   - Invalid control characters

**Solutions:**
- The pipeline has 4-level JSON cleanup built-in
- Most parsing issues resolve automatically
- If persistent, check prompt clarity

### Symptom: Empty results after LLM call

**Check:**
1. Raw response content exists and is not empty
2. JSON structure matches expected format
3. LLM didn't return error message instead of data

**Example good response:**
```json
[
  {
    "section_title": "Основы технологии",
    "section_description": "Объяснение базовых принципов",
    "content_focus": "Образовательный контент",
    "key_points": "Определения, принципы работы",
    "subsections": ["Что это", "Как работает"]
  }
]
```

---

## 🚀 Performance Optimization

### Slow pipeline execution

**Check current settings in `src/config.py`:**
```python
CONCURRENT_REQUESTS = 5    # Parallel URL scraping
TOP_N_SOURCES = 5          # Number of top sources to process
MIN_CONTENT_LENGTH = 10000 # Minimum article length
```

**Optimization tips:**
1. **Reduce sources**: Lower `TOP_N_SOURCES` to 3-4
2. **Increase concurrency**: Raise `CONCURRENT_REQUESTS` to 8-10
3. **Skip link processing**: Disable in config if not needed
4. **Use faster models**: Configure faster LLM models

### Memory issues

**Symptoms:** Pipeline crashes or hangs during processing

**Solutions:**
1. Process fewer sources at once
2. Clear output folder between runs
3. Monitor with: `python -m psutil` during execution

---

## 📝 Content Quality Issues

### Poor structure extraction

**Check:**
1. Input articles quality (too short, irrelevant)
2. LLM prompt effectiveness in `prompts/basic_articles/01_extract.txt`
3. Raw LLM responses for actual extracted structures

**Typical issues:**
- Articles too generic or promotional
- Non-English content confusing the LLM
- Technical articles without clear structure

### Generated article quality problems

**Debug process:**
1. Check `ultimate_structure.json` - is it comprehensive?
2. Check `wordpress_data.json` - does it contain proper content?
3. Check `wordpress_data_final.json` - was editorial review successful?

**Common fixes:**
- Better source selection (check scoring phase)
- More detailed ultimate structure
- Clear topic specification

---

## ⚙️ Configuration Problems

### Missing API keys

**Error:** `API key not found for provider`

**Solution:** Check `.env` file contains:
```bash
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Firecrawl API issues

**Errors:**
- `502 Bad Gateway` - Firecrawl server issues (retry later)
- `Rate limit exceeded` - Too many requests
- `Invalid API key` - Check FIRECRAWL_API_KEY

**Solutions:**
1. Check API key validity
2. Reduce concurrent requests
3. Wait and retry for server issues

### WordPress publication fails

**Check:**
1. WordPress credentials in `.env`
2. Site accessibility: https://ailynx.ru
3. WordPress API endpoints working

**Debug WordPress:**
```bash
# Test connection manually
curl -u "admin:your_password" "https://ailynx.ru/wp-json/wp/v2/posts"
```

---

## 🔧 Quick Fixes

### Pipeline stuck at specific stage

1. **Check logs:** Look for error messages
2. **Check raw responses:** See if LLM responded
3. **Kill and restart:** Stop pipeline and run again
4. **Clear output:** Remove output folder and retry

### Unexpected results

1. **Check topic specification:** Be specific and clear
2. **Check source quality:** Review selected articles
3. **Check prompts:** Verify prompts make sense for your use case
4. **Check models:** Ensure LLM models are responding correctly

### Performance monitoring

```bash
# Monitor token usage
cat output/Your_Topic/token_usage_report.json

# Check pipeline progress
tail -f app.log

# Monitor memory usage during run
top -pid $(pgrep -f "python main.py")
```

---

## 📞 When All Else Fails

1. **Clear everything:** Delete output folder completely
2. **Restart fresh:** Run pipeline with simple test topic
3. **Check dependencies:** `pip install -r requirements.txt`
4. **Update models:** Check if models in config are still available
5. **Manual debugging:** Run pipeline step by step, checking each stage

Most issues are resolved by checking the raw LLM responses and ensuring prompts are clear and API keys are valid.