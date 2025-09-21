# Link Scoring System Documentation

## Overview

This document describes the heuristic scoring system used by the `LinkProcessor` class to automatically select the best links from search results. The system prioritizes official documentation, academic sources, and authoritative domains while penalizing forums, blogs, and unreliable sources.

## Scoring Algorithm

The scoring system starts with a base score of 1.0 and applies various bonuses and penalties based on domain authority, path structure, and other quality indicators.

### Base Score Calculation

```python
score = 1.0  # Starting point for all candidates
```

### Bonuses (in order of priority)

| Criteria | Bonus | Examples |
|----------|-------|----------|
| **Official Documentation** | +10.0 | `docs.*`, `api.*`, `developer.*` |
| **Priority Domains (Whitelist)** | +10.0 | `python.langchain.com`, `ai.google.dev` |
| **Universities & Organizations** | +8.0 | `.edu`, `.org` domains |
| **Major Tech Companies** | +6.0 | Google, Microsoft, Apple, Amazon, Meta, NVIDIA, OpenAI, Anthropic |
| **Authority Patterns** | +5.0 | GitHub.io, specific authority patterns |
| **GitHub Repositories** | +4.0 | `github.com`, `github.io` |
| **Priority Paths** | +1.0 to +3.0 | `/docs`, `/api`, `/pricing` (pricing gets +3.0) |
| **HTTPS Protocol** | +0.5 | Secure connections |

### Penalties

| Criteria | Penalty | Examples |
|----------|---------|----------|
| **Blocked Domains** | -15.0 | Reddit, Medium, Dev.to, etc. |
| **Personal Blogs** | -10.0 | Medium.com, Hackernoon.com, Blogger.com |
| **Community Forums** | -5.0 | `community.*`, `forum.*`, `answers.*` |

## Priority Domains Whitelist

The system maintains a curated list of official domains in `filters/preferred_domains.json`:

### AI/ML Platforms
- `python.langchain.com`, `js.langchain.com` - LangChain documentation
- `docs.haystack.deepset.ai` - Haystack framework
- `ai.google.dev`, `ai.google` - Google AI documentation
- `openai.com`, `platform.openai.com` - OpenAI official sites
- `anthropic.com`, `docs.anthropic.com` - Anthropic documentation

### Tech Companies
- `learn.microsoft.com`, `docs.microsoft.com` - Microsoft documentation
- `developers.google.com`, `cloud.google.com` - Google developer resources
- `docs.github.com` - GitHub documentation
- `developer.apple.com` - Apple developer documentation

### Academic & Research
- `arxiv.org` - Academic papers
- `papers.nips.cc` - NeurIPS proceedings
- `acl-web.org` - Association for Computational Linguistics
- `ieee.org` - IEEE publications

## Scoring Examples

### Example 1: LangChain Documentation Selection

**GeeksforGeeks:**
```
Base score: 1.0
+ HTTPS bonus: +0.5
= Total: 1.5 points
```

**Official LangChain (python.langchain.com/docs/tutorials/):**
```
Base score: 1.0
+ Priority domain bonus: +10.0 (python.langchain.com in whitelist)
+ Priority path bonus: +1.0 (/docs)
+ HTTPS bonus: +0.5
= Total: 12.5 points
```

### Example 2: Google AI Documentation

**Unstract Docs (docs.unstract.com):**
```
Base score: 1.0
+ Official documentation bonus: +10.0 (starts with docs.)
+ HTTPS bonus: +0.5
= Total: 11.5 points
```

**Google AI Official (ai.google.dev):**
```
Base score: 1.0
+ Priority domain bonus: +10.0 (ai.google.dev in whitelist)
+ HTTPS bonus: +0.5
= Total: 11.5 points
```

*Note: When scores are equal, the system selects based on search result position*

## Configuration Files

### filters/preferred_domains.json

Contains three main sections:

1. **priority_domains**: Official domains that receive +10.0 bonus
2. **priority_paths**: URL paths that indicate documentation (+1.0 to +3.0 bonus)
3. **blocked_domains**: Domains that receive severe penalties (-15.0)

### Adding New Official Domains

To add support for a new technology's official documentation:

1. Edit `filters/preferred_domains.json`
2. Add all official domain variants to `priority_domains` array:
   ```json
   "docs.newframework.com",
   "api.newframework.com",
   "www.newframework.com"
   ```
3. Test the scoring with example URLs

## Implementation Details

The scoring logic is implemented in:
- File: `src/link_processor.py`
- Method: `_score_candidates()`
- Lines: Проверить актуальные номера строк в коде

### Selection Process

1. **Search Candidates**: Firecrawl API finds potential links
2. **Apply Scoring**: Each candidate gets scored using the heuristic system
3. **Sort by Score**: Candidates sorted in descending order by score
4. **Select Best**: Highest scoring candidate is chosen
5. **Fallback**: If multiple candidates have equal scores, first in search results is selected

## Quality Assurance

The system ensures quality by:

1. **Preferring Official Sources**: Official documentation gets highest bonuses
2. **Academic Authority**: Universities and research institutions get high scores
3. **Blocking Low-Quality Sources**: Forums, blogs, and social media are penalized
4. **Path-based Detection**: URLs with `/docs`, `/api` paths get additional bonuses
5. **Company Authority**: Major tech companies get recognition bonuses

## Maintenance

Regular maintenance should include:

1. **Domain List Updates**: Add new official domains as technologies evolve
2. **Penalty Review**: Ensure blocked domains list stays current
3. **Score Balance**: Monitor scoring balance to ensure official sources consistently win
4. **False Positive Check**: Verify that quality unofficial sources aren't over-penalized

## Debugging

To debug scoring decisions:

1. Check `selected_links.json` for chosen URLs and scores
2. Review `candidates.json` for all available options
3. Manually calculate expected scores using the table above
4. Verify domain presence in `preferred_domains.json`

## Future Improvements

Potential enhancements:

1. **Machine Learning Scoring**: Train a model on curated good/bad link examples
2. **Content Quality Analysis**: Analyze actual page content for authority indicators
3. **Link Freshness**: Consider publication date and update frequency
4. **Domain Reputation**: Integrate with domain authority services
5. **User Feedback**: Collect feedback on link quality to improve scoring