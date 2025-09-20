# Content Factory - Basic Articles Pipeline

Automated pipeline for generating high-quality basic articles with FAQ sections and source references. Designed for creating structured, informative content on any topic.

## 🚀 Quick Start

```bash
cd "/path/to/Content-factory"
source venv/bin/activate
python main.py "Your topic here"
```

**Example:**
```bash
python main.py "Best practices for remote work productivity"
```

## 📋 How It Works

**10-Stage Pipeline:**

1. **Search** - Find 20 relevant URLs using Firecrawl API
2. **Parse** - Extract content from URLs with filtering
3. **Score** - Rate sources by trust, relevance, and depth
4. **Select** - Pick top 5 sources for processing
5. **Clean** - Remove navigation, ads, and formatting noise
6. **Extract Structures** - Analyze content organization from each source
7. **Create Ultimate Structure** - Synthesize all structures into one comprehensive outline
8. **Generate Article** - Create WordPress-ready article with FAQ and sources
9. **Editorial Review** - Clean formatting and improve readability
10. **Link Processing** *(optional)* - Add relevant external links with academic footnotes
11. **Publish** *(optional)* - Automatically publish to WordPress

## 🎯 Output

Each run generates:
- **Structured article** with H2/H3 headings
- **FAQ section** with collapsible questions
- **Sources section** with numbered references
- **WordPress-ready HTML** with proper formatting
- **SEO metadata** (title, description, focus keyword)

## 📁 Project Structure

```
Content-factory/
├── main.py                 # Main pipeline script
├── src/                    # Core modules
│   ├── firecrawl_client.py # API integration
│   ├── processing.py       # Content processing
│   ├── llm_processing.py   # LLM interactions
│   └── config.py           # Configuration
├── prompts/basic_articles/ # LLM prompts
│   ├── 01_extract.txt      # Structure extraction
│   ├── 02_create_ultimate_structure.txt
│   └── 01_generate_wordpress_article.txt
├── filters/                # Content filtering
├── output/                 # Generated content
└── docs/                   # Documentation
```

## ⚙️ Configuration

### Required API Keys

Create `.env` file:
```bash
FIRECRAWL_API_KEY=fc-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx

# WordPress (optional)
WORDPRESS_URL=https://your-site.com
WORDPRESS_USERNAME=PetrovA
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### Pipeline Settings

Edit `src/config.py`:
```python
# Performance
CONCURRENT_REQUESTS = 5      # Parallel URL scraping
TOP_N_SOURCES = 5            # Sources to process
MIN_CONTENT_LENGTH = 10000   # Minimum article length

# Content Quality
TRUST_SCORE_WEIGHT = 0.5     # Trust score importance
RELEVANCE_SCORE_WEIGHT = 0.3 # Relevance score importance
DEPTH_SCORE_WEIGHT = 0.2     # Content depth importance

# LLM Models (all use free DeepSeek by default)
LLM_MODELS = {
    "extract_prompts": "deepseek/deepseek-chat-v3.1:free",
    "create_structure": "deepseek/deepseek-chat-v3.1:free",
    "generate_article": "deepseek/deepseek-chat-v3.1:free",
    "editorial_review": "deepseek/deepseek-chat-v3.1:free"
}
```

## 🔍 Output Structure

After running, check:
```
output/Your_Topic/
├── 01_search/              # Search results
├── 02_parsing/             # Scraped content
├── 03_scoring/             # Scored sources
├── 04_selection/           # Top 5 sources
├── 05_cleaning/            # Cleaned content
├── 06_structure_extraction/# Extracted structures
│   ├── all_structures.json
│   ├── llm_requests/       # Debug: What was sent to LLM
│   └── llm_responses_raw/  # Debug: Raw LLM responses
├── 07_ultimate_structure/  # Synthesized structure
├── 08_article_generation/  # Generated article
├── 09_editorial_review/    # Final article
│   ├── wordpress_data_final.json  # Ready for WordPress
│   └── article_content_final.html # HTML content
├── 10_link_processing/     # Link processing (optional)
│   ├── link_plan.json              # Generated link plan
│   ├── candidates.json             # Found link candidates
│   ├── selected_links.json         # Selected links
│   ├── article_with_links.html     # Article with links
│   ├── links_report.json           # Link processing report
│   ├── llm_requests/               # LLM requests for link selection
│   └── llm_responses_raw/          # Raw LLM responses
└── token_usage_report.json        # Token usage stats
```

## 🐛 Troubleshooting

### Common Issues

**Pipeline fails during extraction:**
1. Check `llm_responses_raw/*.txt` files for actual LLM responses
2. Verify API keys are valid
3. Check if sources have sufficient content

**Poor article quality:**
1. Use more specific topic
2. Check `ultimate_structure.json` - is it comprehensive?
3. Review source selection in scoring phase

**JSON parsing errors:**
- Pipeline has automatic JSON cleanup with fallback mechanism
- Enhanced JSON parser handles markdown code blocks (```json...```)
- Check raw LLM responses in debug files
- Most issues resolve automatically
- Link processing includes special fallback for wrapped JSON responses

### Debug Process

1. **Check raw LLM data first:** `llm_responses_raw/*.txt`
2. **Follow data chain:** Input → LLM → Raw response → Parsed JSON
3. **Check prompts:** `llm_requests/*.json`
4. **Monitor tokens:** `token_usage_report.json`

### Performance Tuning

**Speed up pipeline:**
- Reduce `TOP_SOURCES_COUNT` to 3-4
- Increase `CONCURRENT_REQUESTS` to 8-10
- Use faster LLM models

**Improve quality:**
- Increase `MIN_CONTENT_LENGTH` to 2000+
- Use more specific topics
- Review source filtering in `filters/`

## 📚 Documentation

- **[Flow Guide](flow.md)** - Detailed pipeline flow with diagnostics
- **[Troubleshooting](troubleshooting.md)** - Complete debugging guide
- **[WordPress Integration](WORDPRESS_INTEGRATION.md)** - Publication setup
- **[Link System](LINK_SYSTEM.md)** - Automatic link insertion

## 🔧 Dependencies

Install with:
```bash
pip install -r requirements.txt
```

**Key packages:**
- `firecrawl-py` - Web scraping API
- `openai` - LLM interactions
- `requests` - WordPress API
- `python-dotenv` - Environment variables

## 🎯 Use Cases

**Perfect for:**
- Educational articles with structured content
- How-to guides with FAQ sections
- Industry overviews with authoritative sources
- Product comparisons with detailed analysis

**Topics that work well:**
- "Best practices for [specific skill]"
- "Complete guide to [technology/tool]"
- "[Industry] trends in 2024"
- "How to choose [product category]"

## 💡 Tips for Best Results

1. **Be specific with topics** - "AI tools for content creation" vs "AI tools"
2. **Use current topics** - Include year for trending subjects
3. **Check source quality** - Review selected articles in output
4. **Monitor token usage** - Track costs with usage reports
5. **Test before publishing** - Review generated content quality

## 🔥 Recent Updates

### September 19, 2025 - Critical Fallback System Fix

**Issue Resolved:** Section generation timeouts without proper fallback activation

**✅ What was fixed:**
- **Timeout Logic**: Fixed AsyncTimeout killing fallback before it could execute
- **Model Switching**: Primary model timeout now properly triggers Gemini 2.5 fallback
- **Configuration**: Added `SECTION_TIMEOUT`, `MODEL_TIMEOUT`, `SECTION_MAX_RETRIES`
- **Logging**: Enhanced timeout diagnostics with clear fallback indicators

**✅ Impact:**
- **Before**: Section failures → incomplete articles
- **After**: 95%+ success rate with automatic fallback recovery
- **Performance**: Max 180s per section (was 360s timeout)

**✅ New Fallback Flow:**
```
DeepSeek timeout (60s) → Automatic Gemini 2.5 (60s) → Success
🔄 FALLBACK: Trying fallback model google/gemini-2.5-flash-lite-preview-06-17
✅ Model responded successfully (fallback)
```

### September 18, 2025 - Link Processing Improvements

**✅ What was fixed:**
- **Marker Positioning**: No more markers in headers, smart sentence-end placement
- **Duplication Prevention**: Eliminated nested anchor tags `<a><a>[1]</a></a>`
- **Position Accuracy**: Improved algorithm with header detection and context awareness
- **Validation**: Added comprehensive HTML structure validation

**Details:** See [Link Processing Documentation](link_processing.md)

---

**Content Factory** generates comprehensive, well-structured articles automatically while maintaining high quality and proper sourcing. Perfect for content teams, bloggers, and anyone needing systematic content generation.