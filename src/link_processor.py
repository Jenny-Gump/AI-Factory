import asyncio
import aiohttp
import json
import re
import time
import os
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

from src.config import FIRECRAWL_API_KEY
from src.logger_config import logger
from src.token_tracker import TokenTracker
from src.llm_processing import _load_and_prepare_messages, _make_llm_request_with_retry, save_llm_interaction, _parse_json_from_response


class LinkProcessor:
    """Processes links for articles - creates search queries, finds candidates, and applies links."""

    def __init__(self):
        if not FIRECRAWL_API_KEY:
            raise ValueError("FIRECRAWL_API_KEY is not set in the environment variables.")

        self.base_url = "https://api.firecrawl.dev/v2"
        self.headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json",
        }

        # Load preferred domains
        try:
            with open('filters/preferred_domains.json', 'r', encoding='utf-8') as f:
                self.preferred_domains = json.load(f)
        except FileNotFoundError:
            logger.warning("filters/preferred_domains.json not found, using default domains")
            self.preferred_domains = {
                "priority_domains": [
                    "docs.", "developer.", "w3.org", "ietf.org", "iso.org", "nist.gov",
                    "arxiv.org", "docs.github.com", "learn.microsoft.com",
                    "developers.google.com", "github.com"
                ],
                "priority_paths": [
                    "/docs", "/developer", "/api", "/spec", "/whitepaper", "/documentation"
                ],
                "blocked_domains": [
                    "reddit.com", "stackoverflow.com", "medium.com", "hackernoon.com",
                    "dev.to", "blogger.com", "wordpress.com", "quora.com"
                ]
            }

    async def process_links(self, wordpress_data: Dict[str, Any], topic: str, base_path: str,
                          token_tracker: TokenTracker, active_models: Dict[str, str]) -> Dict[str, Any]:
        """
        Main entry point for link processing pipeline.

        Args:
            wordpress_data: Generated WordPress article data with HTML content
            topic: Article topic
            base_path: Base path for saving artifacts
            token_tracker: Token usage tracker
            active_models: Active model configuration

        Returns:
            Updated wordpress_data with processed links
        """
        logger.info("=== Starting Link Processing Pipeline ===")
        start_time = time.time()

        try:
            # Step 1: Create link plan
            logger.info("Step 1: Creating link plan...")
            link_plan, draft_with_markers = await self.create_link_plan(
                wordpress_data.get('content', ''), topic, base_path, token_tracker,
                active_models.get('link_planning', active_models.get('extract_prompts'))
            )

            if not link_plan:
                logger.warning("No link plan generated, skipping link processing")
                return wordpress_data

            # Step 2: Search candidates
            logger.info("Step 2: Searching for link candidates...")
            candidates = await self.search_candidates(link_plan, base_path)

            # Step 3: Select best links
            logger.info("Step 3: Selecting best links...")
            selected_links = await self.select_links(candidates, link_plan, base_path,
                                                   token_tracker, active_models.get('link_selection', active_models.get('extract_prompts')))

            # Step 4: Apply links to content
            logger.info("Step 4: Applying links to content...")
            final_content = self.apply_links(draft_with_markers, selected_links, base_path)

            # Update wordpress_data with processed content
            wordpress_data_with_links = wordpress_data.copy()
            wordpress_data_with_links['content'] = final_content

            # Generate report
            self.save_links_report(link_plan, selected_links, base_path, time.time() - start_time)

            logger.info(f"=== Link Processing Complete ({time.time() - start_time:.1f}s) ===")
            return wordpress_data_with_links

        except Exception as e:
            logger.error(f"Link processing failed: {e}")
            # Return original data on failure
            return wordpress_data

    async def create_link_plan(self, html_content: str, topic: str, base_path: str,
                             token_tracker: TokenTracker, model_name: str) -> Tuple[List[Dict], str]:
        """
        Step 1: Generate link plan with markers and search queries.

        Returns:
            Tuple of (link_plan, draft_with_markers)
        """
        try:
            # Load and prepare LLM messages
            messages = _load_and_prepare_messages(
                "basic_articles",
                "01_5_link_planning",
                {"topic": topic, "html_content": html_content}
            )

            # Make LLM request
            response_obj, actual_model = _make_llm_request_with_retry(
                stage_name="link_planning",
                model_name=model_name,
                messages=messages,
                token_tracker=token_tracker,
                temperature=0.3,
                timeout=60
            )

            content = response_obj.choices[0].message.content

            # Save interaction
            save_llm_interaction(
                base_path=base_path,
                stage_name="link_planning",
                messages=messages,
                response=content,
                request_id="link_plan"
            )

            # Parse JSON response
            try:
                parsed_json = json.loads(content)
                if not isinstance(parsed_json, dict):
                    logger.error("Invalid link plan JSON structure - not a dict")
                    return [], html_content

                link_plan = parsed_json.get('link_plan', [])
                draft_with_markers = parsed_json.get('draft_with_markers', html_content)

                if not isinstance(link_plan, list):
                    logger.error("Invalid link plan JSON structure - link_plan not a list")
                    return [], html_content

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse link plan JSON: {e}")
                return [], html_content

            # Save artifacts
            self._save_artifact(link_plan, base_path, 'link_plan.json')
            self._save_artifact(draft_with_markers, base_path, 'draft_with_markers.html')

            logger.info(f"Generated {len(link_plan)} link queries with markers")
            return link_plan, draft_with_markers

        except Exception as e:
            logger.error(f"Failed to create link plan: {e}")
            return [], html_content

    async def search_candidates(self, link_plan: List[Dict], base_path: str) -> Dict[str, List[Dict]]:
        """
        Step 2: Search for candidate URLs for each query.

        Returns:
            Dict mapping ref_id to list of candidate URLs
        """
        candidates = {}

        # Limit concurrent requests
        semaphore = asyncio.Semaphore(5)
        timeout = aiohttp.ClientTimeout(total=6)

        async def search_single_query(session: aiohttp.ClientSession, query_info: Dict) -> Tuple[str, List[Dict]]:
            async with semaphore:
                ref_id = query_info.get('ref_id')
                query = query_info.get('query', '')

                logger.info(f"Searching for ref_id={ref_id}: '{query}'")

                try:
                    url = f"{self.base_url}/search"
                    json_data = {
                        "query": query,
                        "limit": 5
                    }

                    async with session.post(url, json=json_data) as response:
                        response.raise_for_status()
                        search_results = await response.json()
                        results = search_results.get('data', {}).get('web', [])

                        # Filter and validate candidates
                        valid_candidates = []
                        for result in results[:5]:  # Max 5 per query
                            if await self._validate_candidate(session, result):
                                valid_candidates.append(result)

                        logger.info(f"Found {len(valid_candidates)} valid candidates for ref_id={ref_id}")
                        return ref_id, valid_candidates

                except Exception as e:
                    logger.error(f"Search failed for ref_id={ref_id}: {e}")
                    return ref_id, []

        # Execute searches concurrently
        async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
            tasks = [search_single_query(session, query_info) for query_info in link_plan]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Search task failed: {result}")
                    continue
                ref_id, urls = result
                candidates[ref_id] = urls

        # Save candidates
        self._save_artifact(candidates, base_path, 'candidates.json')

        total_candidates = sum(len(urls) for urls in candidates.values())
        logger.info(f"Found {total_candidates} total candidates across {len(candidates)} queries")

        return candidates

    async def _validate_candidate(self, session: aiohttp.ClientSession, result: Dict) -> bool:
        """Validate a single candidate URL with HEAD request and domain filtering."""
        url = result.get('url', '')
        if not url:
            return False

        try:
            # Parse domain
            domain = urlparse(url).netloc.lower()

            # Check blocked domains
            for blocked in self.preferred_domains.get('blocked_domains', []):
                if blocked in domain:
                    return False

            # Quick HEAD check with short timeout
            head_timeout = aiohttp.ClientTimeout(total=2)
            async with aiohttp.ClientSession(timeout=head_timeout) as head_session:
                async with head_session.head(url) as response:
                    return response.status == 200

        except Exception:
            return False

    async def select_links(self, candidates: Dict[str, List[Dict]], link_plan: List[Dict],
                          base_path: str, token_tracker: TokenTracker, model_name: str) -> Dict[str, Dict]:
        """
        Step 3: Select best link for each ref_id using heuristics + LLM tiebreaker.

        Returns:
            Dict mapping ref_id to selected link info
        """
        selected_links = {}

        for query_info in link_plan:
            ref_id = query_info.get('ref_id')
            hint = query_info.get('hint', '')
            query_candidates = candidates.get(ref_id, [])

            if not query_candidates:
                logger.warning(f"No candidates for ref_id={ref_id}")
                selected_links[ref_id] = {
                    'chosen_url': None,
                    'chosen_title': None,
                    'reason': 'No candidates found'
                }
                continue

            # Apply heuristic scoring
            scored_candidates = self._score_candidates(query_candidates)

            if len(scored_candidates) == 1:
                # Only one candidate - select it
                best = scored_candidates[0]
                selected_links[ref_id] = {
                    'chosen_url': best['url'],
                    'chosen_title': best.get('title', 'Link'),
                    'reason': f"Single candidate (score: {best['score']:.2f})"
                }
            elif len(scored_candidates) > 1:
                # Multiple candidates - use LLM tiebreaker
                best_candidate = await self._llm_tiebreaker(
                    scored_candidates[:3], hint, token_tracker, model_name, base_path, ref_id
                )

                if best_candidate:
                    selected_links[ref_id] = {
                        'chosen_url': best_candidate['url'],
                        'chosen_title': best_candidate.get('title', 'Link'),
                        'reason': f"LLM selection (score: {best_candidate['score']:.2f})"
                    }
                else:
                    selected_links[ref_id] = {
                        'chosen_url': None,
                        'chosen_title': None,
                        'reason': 'LLM could not select'
                    }
            else:
                selected_links[ref_id] = {
                    'chosen_url': None,
                    'chosen_title': None,
                    'reason': 'No valid candidates after scoring'
                }

        # Save selected links
        self._save_artifact(selected_links, base_path, 'selected_links.json')

        selected_count = sum(1 for link in selected_links.values() if link['chosen_url'])
        logger.info(f"Selected {selected_count}/{len(selected_links)} links")

        return selected_links

    def _score_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Apply enhanced heuristic scoring to candidates."""
        import re
        scored = []

        # Authority patterns for automatic detection
        AUTHORITY_PATTERNS = [
            r'docs\.[a-z\-]+\.com',     # docs.*
            r'developer\.[a-z\-]+\.com', # developer.*
            r'api\.[a-z\-]+\.com',      # api.*
            r'[a-z\-]+\.github\.io',    # *.github.io
            r'.*\.edu',                 # universities
            r'.*\.gov',                 # government
            r'.*\.org'                  # organizations
        ]

        for candidate in candidates:
            url = candidate.get('url', '')
            title = candidate.get('title', '')
            domain = urlparse(url).netloc.lower()
            path = urlparse(url).path.lower()

            score = 1.0  # Base score

            # HIGH PRIORITY: Official documentation (+10.0)
            if any(word in domain for word in ['docs.', 'api.', 'developer.']):
                score += 10.0

            # HIGH PRIORITY: Universities and standards (+8.0)
            if domain.endswith('.edu') or domain.endswith('.org'):
                score += 8.0

            # HIGH PRIORITY: Major tech companies (+6.0)
            major_tech = ['google', 'microsoft', 'apple', 'amazon', 'meta', 'nvidia', 'openai', 'anthropic']
            if any(tech in domain for tech in major_tech):
                score += 6.0

            # MEDIUM PRIORITY: GitHub official repos (+4.0)
            if 'github.io' in domain or 'github.com' in domain:
                score += 4.0

            # Authority pattern detection (+5.0)
            for pattern in AUTHORITY_PATTERNS:
                if re.match(pattern, domain):
                    score += 5.0
                    break

            # Priority domain bonuses (+2.0)
            for priority_domain in self.preferred_domains.get('priority_domains', []):
                if priority_domain in domain:
                    score += 2.0
                    break

            # Priority path bonuses (+3.0 for pricing, +1.0 for others)
            for priority_path in self.preferred_domains.get('priority_paths', []):
                if priority_path in path:
                    if 'pricing' in priority_path:
                        score += 3.0
                    else:
                        score += 1.0
                    break

            # PENALTIES: Community forums and personal blogs (-5.0)
            forum_indicators = ['community.', 'forum.', 'answers.', 'discuss.']
            if any(indicator in domain for indicator in forum_indicators):
                score -= 5.0

            # HARSH PENALTIES: Personal blogs and social media (-10.0)
            blog_indicators = ['medium.com', 'dev.to', 'hackernoon.com', 'blogger.com']
            if any(blog in domain for blog in blog_indicators):
                score -= 10.0

            # Blocked domain check
            for blocked_domain in self.preferred_domains.get('blocked_domains', []):
                if blocked_domain in domain:
                    score -= 15.0  # Severe penalty
                    break

            # HTTPS bonus (+0.5)
            if url.startswith('https://'):
                score += 0.5

            # Ensure minimum score of 0
            score = max(0.0, score)

            candidate_scored = candidate.copy()
            candidate_scored['score'] = score
            scored.append(candidate_scored)

        # Sort by score descending
        return sorted(scored, key=lambda x: x['score'], reverse=True)

    async def _llm_tiebreaker(self, candidates: List[Dict], hint: str, token_tracker: TokenTracker,
                            model_name: str, base_path: str, ref_id: str) -> Optional[Dict]:
        """Use LLM to select best candidate when heuristics are tied."""
        try:
            # Prepare candidates info for LLM
            candidates_text = ""
            for i, candidate in enumerate(candidates, 1):
                candidates_text += f"{i}. {candidate.get('title', 'No title')} - {candidate['url']}\n"
                if 'description' in candidate:
                    candidates_text += f"   Description: {candidate['description'][:100]}...\n"
                candidates_text += f"   Score: {candidate['score']:.2f}\n\n"

            # Enhanced selection prompt with strict authority hierarchy
            system_prompt = """You are a link selection expert. STRICTLY follow this priority hierarchy:

1. HIGHEST: Official API documentation (docs.openai.com, api.anthropic.com, docs.microsoft.com)
2. HIGH: Official company docs (openai.com, anthropic.com, google.ai, microsoft.com)
3. MEDIUM: Standards organizations (w3.org, ietf.org, ieee.org)
4. MEDIUM: Research papers (arxiv.org, papers.nips.cc, academic .edu domains)
5. LOW: GitHub official repos (github.com, github.io)

NEVER select:
- Community forums (community.*, forum.*, answers.*)
- Personal blogs (medium.com, dev.to, hackernoon.com)
- Question/Answer sites (stackoverflow.com, quora.com)

Prefer official documentation over everything else."""

            user_prompt = f"""Select the MOST AUTHORITATIVE link for: {hint}

Candidates:
{candidates_text}

Respond with ONLY the number (1, 2, or 3) of the most authoritative candidate based on the hierarchy above."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response_obj, actual_model = _make_llm_request_with_retry(
                stage_name="link_selection",
                model_name=model_name,
                messages=messages,
                token_tracker=token_tracker,
                temperature=0.1,
                timeout=30
            )

            content = response_obj.choices[0].message.content.strip()

            # Parse selection
            selection_match = re.search(r'\b([123])\b', content)
            if selection_match:
                selection_idx = int(selection_match.group(1)) - 1
                if 0 <= selection_idx < len(candidates):
                    return candidates[selection_idx]

            logger.warning(f"Could not parse LLM selection for ref_id={ref_id}: '{content}'")
            return candidates[0]  # Return first (highest scored) as fallback

        except Exception as e:
            logger.error(f"LLM tiebreaker failed for ref_id={ref_id}: {e}")
            return candidates[0] if candidates else None

    def apply_links(self, html_content: str, selected_links: Dict[str, Dict], base_path: str) -> str:
        """
        Step 4: Apply selected links to HTML content with academic footnotes.
        Auto-reindexes link numbers to create sequential 1,2,3... numbering.

        Returns:
            HTML content with academic footnotes and references section
        """
        logger.info("Applying links to content...")

        # Filter valid links and create reindex mapping
        valid_links = {}
        reindex_map = {}
        new_index = 1

        for ref_id, link_info in selected_links.items():
            if link_info['chosen_url']:
                valid_links[ref_id] = link_info
                reindex_map[ref_id] = str(new_index)
                new_index += 1

        logger.info(f"Reindexing {len(valid_links)} valid links from {len(selected_links)} total")

        # Replace markers with academic footnotes using new indices
        processed_content = html_content
        references = []

        for old_ref_id, link_info in valid_links.items():
            new_ref_id = reindex_map[old_ref_id]

            # Look for existing anchor tags like <a id='cite-1' href='#ref-1'>[1]</a> OR simple markers [1]
            existing_anchor_pattern = f"<a id='cite-{old_ref_id}' href='#ref-{old_ref_id}'>[{old_ref_id}]</a>"
            simple_marker_pattern = f"\\[{old_ref_id}\\]"

            # Create academic footnote anchor with NEW index
            footnote_anchor = f'<a id="cite-{new_ref_id}" href="#ref-{new_ref_id}" rel="nofollow">[{new_ref_id}]</a>'

            # Try to replace existing anchor first, then simple marker
            if re.search(existing_anchor_pattern, processed_content):
                processed_content = re.sub(existing_anchor_pattern, footnote_anchor, processed_content)
            else:
                processed_content = re.sub(simple_marker_pattern, footnote_anchor, processed_content)

            # Add to references list with NEW index
            references.append({
                'ref_id': new_ref_id,
                'url': link_info['chosen_url'],
                'title': link_info['chosen_title']
            })

        # Remove existing "Источники" section if present
        sources_pattern = r'<h2>Источники</h2>[\s\S]*?</ol>'
        if re.search(sources_pattern, processed_content):
            processed_content = re.sub(sources_pattern, '', processed_content)

        # Add "Полезные ссылки" section at the end if we have references
        if references:
            references_section = '\n\n<h2>Полезные ссылки</h2>\n<ol>\n'

            # Sort references by ref_id to maintain sequential order
            sorted_refs = sorted(references, key=lambda x: int(x['ref_id']))

            for ref in sorted_refs:
                ref_id = ref['ref_id']
                url = ref['url']
                title = ref['title'] or 'Ссылка'

                # Create academic reference entry
                ref_entry = f'     <li id="ref-{ref_id}"><a href="{url}" target="_blank" rel="nofollow noopener">{title}</a><a href="#cite-{ref_id}" aria-label="Вернуться к месту ссылки [{ref_id}]">[↑]</a></li>\n'
                references_section += ref_entry

            references_section += '</ol>'
            processed_content += references_section

        # Save final content
        self._save_artifact(processed_content, base_path, 'article_with_links.html')

        logger.info(f"Applied {len(references)} sequential academic footnotes to content")
        return processed_content

    def save_links_report(self, link_plan: List[Dict], selected_links: Dict[str, Dict],
                         base_path: str, processing_time: float):
        """Generate and save link processing report."""
        total_refs = len(link_plan)
        selected_count = sum(1 for link in selected_links.values() if link['chosen_url'])
        unresolved = [ref_id for ref_id, link in selected_links.items() if not link['chosen_url']]

        # Count domains used
        domains_used = {}
        for link_info in selected_links.values():
            if link_info['chosen_url']:
                domain = urlparse(link_info['chosen_url']).netloc
                domains_used[domain] = domains_used.get(domain, 0) + 1

        report = {
            'total_refs': total_refs,
            'selected': selected_count,
            'success_rate': round(selected_count / total_refs * 100, 1) if total_refs > 0 else 0,
            'unresolved': unresolved,
            'domains_used': domains_used,
            'processing_time_seconds': round(processing_time, 1)
        }

        self._save_artifact(report, base_path, 'links_report.json')

        logger.info(f"Link processing report: {selected_count}/{total_refs} resolved ({report['success_rate']}%)")

    def _save_artifact(self, data: Any, base_path: str, filename: str):
        """Save artifact to file."""
        os.makedirs(base_path, exist_ok=True)
        filepath = os.path.join(base_path, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved artifact: {filepath}")