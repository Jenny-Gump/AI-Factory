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

    def process_links(self, wordpress_data: Dict[str, Any], topic: str, base_path: str,
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

        # Store base path for debugging
        self._current_base_path = base_path

        try:
            # Step 1: Create link plan
            logger.info("Step 1: Creating link plan...")
            link_plan, draft_with_markers = self.create_link_plan(
                wordpress_data.get('content', ''), topic, base_path, token_tracker,
                active_models.get('link_planning', active_models.get('extract_prompts'))
            )

            if not link_plan:
                logger.warning("No link plan generated, skipping link processing")
                return wordpress_data

            # Step 2: Search candidates
            logger.info("Step 2: Searching for link candidates...")
            candidates = self.search_candidates(link_plan, base_path)

            # Step 3: Select best links
            logger.info("Step 3: Selecting best links...")
            selected_links = self.select_links(candidates, link_plan, base_path,
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

    def create_link_plan(self, html_content: str, topic: str, base_path: str,
                             token_tracker: TokenTracker, model_name: str) -> Tuple[List[Dict], str]:
        """
        Step 1: Generate link plan with retries for JSON parsing errors.

        Returns:
            Tuple of (link_plan, draft_with_markers)
        """
        # Prepare HTML for LLM by marking problematic tags
        prepared_html = self._prepare_html_for_llm(html_content)

        # Load and prepare LLM messages
        messages = _load_and_prepare_messages(
            "basic_articles",
            "01_5_link_planning",
            {"topic": topic, "html_content": prepared_html}
        )

        # RETRY LOGIC: 2 LLM attempts before fallback
        content = None
        for attempt in range(1, 3):  # 2 attempts
            try:
                logger.info(f"Creating link plan - attempt {attempt}/2")

                # Make LLM request
                response_obj, actual_model = _make_llm_request_with_retry(
                    stage_name="link_planning",
                    model_name=model_name,
                    messages=messages,
                    token_tracker=token_tracker,
                    base_path=base_path,
                    temperature=0.3,
                )

                content = response_obj.choices[0].message.content

                # Save interaction
                save_llm_interaction(
                    base_path=base_path,
                    stage_name="link_planning",
                    messages=messages,
                    response=content,
                    request_id=f"link_plan_attempt_{attempt}"
                )

                # Try to parse JSON with basic fixes
                try:
                    # Fix missing colons BEFORE parsing
                    fixed_content = re.sub(r'"(context_after|context_before|anchor_text|query|hint|section): ', r'"\1": ', content)
                    parsed_json = json.loads(fixed_content)

                    # Validate structure
                    if isinstance(parsed_json, dict) and 'link_plan' in parsed_json:
                        link_plan = parsed_json['link_plan']
                        if isinstance(link_plan, list) and len(link_plan) > 0:
                            logger.info(f"✅ JSON parsed successfully on attempt {attempt}")

                            # Validate link_plan structure
                            validated_plan = []
                            for item in link_plan:
                                required_fields = ['ref_id', 'anchor_text', 'context_after']
                                if all(field in item and item[field] for field in required_fields):
                                    validated_plan.append(item)
                                else:
                                    logger.warning(f"Skipping invalid plan item (missing fields): {item}")

                            if len(validated_plan) != len(link_plan):
                                logger.warning(f"Filtered {len(link_plan) - len(validated_plan)} invalid items")

                            link_plan = validated_plan

                            if len(link_plan) > 0:
                                # Validate anchors and create artifacts
                                validation_report = self._validate_anchors(html_content, link_plan)
                                self._save_artifact(validation_report, base_path, 'anchor_validation_report.json')

                                draft_with_markers = self._insert_markers_with_smart_positioning(html_content, link_plan)

                                self._save_artifact(link_plan, base_path, 'link_plan.json')
                                self._save_artifact(draft_with_markers, base_path, 'draft_with_markers.html')

                                logger.info(f"Generated {len(link_plan)} link queries with markers")
                                return link_plan, draft_with_markers
                            else:
                                logger.warning(f"No valid plan items after validation on attempt {attempt}")

                    logger.warning(f"Invalid JSON structure on attempt {attempt}")

                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parsing failed on attempt {attempt}: {e}")
                    if attempt == 2:  # Last attempt
                        logger.error("All LLM attempts failed, using enhanced fallback")
                        break
                    else:
                        logger.info("Retrying LLM request...")
                        continue

            except Exception as e:
                logger.error(f"LLM request failed on attempt {attempt}: {e}")
                if attempt == 2:
                    break

        # FALLBACK: Enhanced JSON processing after LLM failures
        if content:
            logger.warning("Using enhanced JSON fallback processing")
            try:
                # Save raw response for debugging
                self._save_artifact(content, base_path, 'llm_responses_raw/link_plan_response.txt')

                parsed_json = _parse_json_from_response(content)
                if isinstance(parsed_json, dict) and 'link_plan' in parsed_json:
                    link_plan = parsed_json['link_plan']
                    if isinstance(link_plan, list):
                        logger.info("✅ Fallback JSON parsing successful")

                        # Validate link_plan structure
                        validated_plan = []
                        for item in link_plan:
                            required_fields = ['ref_id', 'anchor_text', 'context_after']
                            if all(field in item and item[field] for field in required_fields):
                                validated_plan.append(item)
                            else:
                                logger.warning(f"Skipping invalid plan item (missing fields): {item}")

                        if len(validated_plan) != len(link_plan):
                            logger.warning(f"Filtered {len(link_plan) - len(validated_plan)} invalid items")

                        link_plan = validated_plan

                        if len(link_plan) > 0:
                            validation_report = self._validate_anchors(html_content, link_plan)
                            self._save_artifact(validation_report, base_path, 'anchor_validation_report.json')

                            draft_with_markers = self._insert_markers_with_smart_positioning(html_content, link_plan)

                            self._save_artifact(link_plan, base_path, 'link_plan.json')
                            self._save_artifact(draft_with_markers, base_path, 'draft_with_markers.html')

                            return link_plan, draft_with_markers
            except Exception as e:
                logger.error(f"Fallback JSON parsing failed: {e}")

        # Complete failure
        logger.error("All JSON parsing attempts failed")
        return [], html_content

    def _insert_markers_by_position(self, html_content: str, link_plan: List[Dict]) -> str:
        """
        Insert link markers [N] at specified character positions with smart positioning.
        Uses simple markers [N] to avoid duplication issues with apply_links method.

        Args:
            html_content: Original HTML content
            link_plan: List of link plan items with character_position field

        Returns:
            HTML content with inserted simple markers
        """
        if not link_plan:
            return html_content

        # Sort by position in reverse order to maintain correct positions during insertion
        sorted_links = sorted(
            [item for item in link_plan if 'character_position' in item],
            key=lambda x: x['character_position'],
            reverse=True
        )

        result = html_content
        cumulative_offset = 0  # Track total characters added

        # Keep track of insertions for debugging
        insertions = []

        for item in sorted_links:
            ref_id = item.get('ref_id', '')
            position = item.get('character_position', 0)

            # Ensure position is within bounds
            if position < 0 or position > len(result):
                logger.warning(f"Invalid position {position} for ref_id {ref_id} (content length: {len(result)})")
                continue

            # Find the best insertion point near the specified position
            best_position = self._find_best_insertion_point(result, position)

            # Check for existing marker nearby to avoid duplicates
            nearby_content = result[max(0, best_position-20):best_position+20]
            if f'[{ref_id}]' in nearby_content:
                logger.warning(f"Marker [{ref_id}] already exists nearby position {best_position}, skipping")
                continue

            # Create simple marker (no HTML anchor tags here)
            marker = f'[{ref_id}]'

            # Insert marker at the best position
            result = result[:best_position] + marker + result[best_position:]

            # Track insertion for debugging
            insertions.append({
                'ref_id': ref_id,
                'requested_pos': position,
                'actual_pos': best_position,
                'marker': marker
            })

            logger.debug(f"Inserted marker [{ref_id}] at position {best_position} (requested: {position})")

        # Save debugging info if we have a base path (html_content might not be a path)
        try:
            if insertions:
                debug_path = getattr(self, '_current_base_path', '/tmp')
                self._save_artifact(insertions, debug_path, 'marker_insertions_debug.json')
        except Exception as e:
            logger.debug(f"Could not save debug info: {e}")

        logger.info(f"Inserted {len(insertions)} markers into content")
        return result

    def _find_best_insertion_point(self, text: str, target_pos: int) -> int:
        """
        Find the best insertion point near the target position.
        Prefers positions after punctuation, closing tags, or end of words.

        Args:
            text: The text to search in
            target_pos: The target character position

        Returns:
            The best position for inserting the marker
        """
        # Ensure target position is within bounds
        target_pos = max(0, min(target_pos, len(text)))

        # Search window around target position
        window_size = 100  # Increased window for better positioning
        start = max(0, target_pos - window_size//2)
        end = min(len(text), target_pos + window_size//2)

        # Check if we're in a header - if so, move to end of header
        header_check_start = max(0, target_pos - 100)
        header_context = text[header_check_start:target_pos + 50]

        # If we're inside a header, move to after the closing tag
        if '<h' in header_context and '</h' in header_context:
            header_end = text.find('>', target_pos)
            if header_end != -1:
                target_pos = header_end + 1
                # Recalculate window
                start = max(0, target_pos - window_size//2)
                end = min(len(text), target_pos + window_size//2)

        # Priority positions (in order of preference with scores)
        candidates = []

        # High priority: After sentence endings
        for sentence_end in ['. ', '.\n', '.</p>', '.«', '.»']:
            pos = text.find(sentence_end, start, end)
            while pos != -1 and pos < end:
                candidate_pos = pos + len(sentence_end) - 1
                distance = abs(candidate_pos - target_pos)
                score = 100 - distance * 0.5  # High score, small distance penalty
                candidates.append((candidate_pos, score, f'sentence_end_{sentence_end.strip()}'))
                pos = text.find(sentence_end, pos + 1, end)

        # Medium priority: After punctuation
        for punct in [', ', '; ', ': ', ') ', '» ', '« ', '. ']:
            pos = text.find(punct, start, end)
            while pos != -1 and pos < end:
                candidate_pos = pos + len(punct) - 1
                distance = abs(candidate_pos - target_pos)
                score = 70 - distance * 0.8
                candidates.append((candidate_pos, score, f'punctuation_{punct.strip()}'))
                pos = text.find(punct, pos + 1, end)

        # Medium priority: After closing tags
        for tag in ['</p>', '</li>', '</strong>', '</em>', '</code>']:
            pos = text.find(tag, start, end)
            while pos != -1 and pos < end:
                candidate_pos = pos + len(tag)
                distance = abs(candidate_pos - target_pos)
                score = 60 - distance * 1.0
                candidates.append((candidate_pos, score, f'closing_tag_{tag}'))
                pos = text.find(tag, pos + 1, end)

        # Low priority: After spaces (word boundaries)
        pos = start
        while pos < end:
            if text[pos] == ' ' and pos > 0 and text[pos-1] not in ' \n\t':
                distance = abs(pos + 1 - target_pos)
                score = 30 - distance * 1.5
                candidates.append((pos + 1, score, 'word_boundary'))
            pos += 1

        # Find best candidate
        if candidates:
            best_candidate = max(candidates, key=lambda x: x[1])
            best_pos, best_score, reason = best_candidate
            logger.debug(f"Best insertion point: pos={best_pos}, score={best_score:.1f}, reason={reason}, distance={abs(best_pos - target_pos)}")
            return best_pos

        # Fallback: move to end of current word
        pos = target_pos
        while pos < len(text) and text[pos] not in ' \t\n<>.,;:!?()[]{}\"\'':
            pos += 1

        logger.debug(f"Fallback insertion point: pos={pos} (moved from {target_pos})")
        return pos

    def search_candidates(self, link_plan: List[Dict], base_path: str) -> Dict[str, List[Dict]]:
        """
        Step 2: Search for candidate URLs for each query.

        Returns:
            Dict mapping ref_id to list of candidate URLs
        """
        candidates = {}

        def search_single_query(query_info: Dict) -> Tuple[str, List[Dict]]:
            ref_id = query_info.get('ref_id')
            query = query_info.get('query', '')

            logger.info(f"Searching for ref_id={ref_id}: '{query}'")

            try:
                url = f"{self.base_url}/search"
                json_data = {
                    "query": query,
                    "limit": 5
                }

                import requests
                response = requests.post(url, json=json_data, headers=self.headers, timeout=6)
                response.raise_for_status()
                search_results = response.json()
                results = search_results.get('data', {}).get('web', [])

                # Filter and validate candidates
                valid_candidates = []
                for result in results[:5]:  # Max 5 per query
                    if self._validate_candidate_sync(result):
                        valid_candidates.append(result)

                logger.info(f"Found {len(valid_candidates)} valid candidates for ref_id={ref_id}")
                return ref_id, valid_candidates

            except Exception as e:
                logger.error(f"Search failed for ref_id={ref_id}: {e}")
                return ref_id, []

        # Execute searches sequentially with delays
        for i, query_info in enumerate(link_plan):
            if i > 0:
                import time
                time.sleep(2)  # 2 second delay between requests

            ref_id, urls = search_single_query(query_info)
            candidates[ref_id] = urls

        # Save candidates
        self._save_artifact(candidates, base_path, 'candidates.json')

        total_candidates = sum(len(urls) for urls in candidates.values())
        logger.info(f"Found {total_candidates} total candidates across {len(candidates)} queries")

        return candidates

    def _validate_candidate_sync(self, result: Dict) -> bool:
        """Validate a single candidate URL with HEAD request and domain filtering."""
        url = result.get('url', '')
        if not url:
            return False

        try:
            # Parse domain
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()

            # Check blocked domains
            for blocked in self.preferred_domains.get('blocked_domains', []):
                if blocked in domain:
                    return False

            # Quick HEAD check with short timeout
            import requests
            response = requests.head(url, timeout=2)
            return response.status_code == 200

        except Exception:
            return False

    def select_links(self, candidates: Dict[str, List[Dict]], link_plan: List[Dict],
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
            anchor_text = query_info.get('anchor_text', '')
            context_before = query_info.get('context_before', '')
            context_after = query_info.get('context_after', '')
            context = f"{context_before} {context_after}".strip()

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
                # Multiple candidates - use best scoring candidate (skip slow LLM selection)
                best_candidate = scored_candidates[0]  # Already sorted by score
                selected_links[ref_id] = {
                    'chosen_url': best_candidate['url'],
                    'chosen_title': best_candidate.get('title', 'Link'),
                    'reason': f"Heuristic selection (score: {best_candidate.get('score', 0):.2f})"
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

            # Priority domain bonuses (+10.0) - Official sources get high priority
            for priority_domain in self.preferred_domains.get('priority_domains', []):
                if priority_domain in domain:
                    score += 10.0
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

    async def _llm_select_best_candidate(self, candidates: List[Dict], hint: str, anchor_text: str,
                                       context: str, token_tracker: TokenTracker, model_name: str,
                                       base_path: str, ref_id: str) -> Optional[Dict]:
        """Use LLM with proper prompt file to select best candidate."""
        try:
            # Load and prepare LLM messages using the proper prompt file
            messages = _load_and_prepare_messages(
                "basic_articles",
                "02_link_selection",
                {
                    "anchor_text": anchor_text,
                    "context": context,
                    "candidates": json.dumps(candidates, indent=2, ensure_ascii=False)
                }
            )

            response_obj, actual_model = _make_llm_request_with_retry(
                stage_name="link_selection",
                model_name=model_name,
                messages=messages,
                token_tracker=token_tracker,
                base_path=base_path,
                temperature=0.1,
            )

            content = response_obj.choices[0].message.content.strip()

            # Save interaction for debugging
            save_llm_interaction(
                base_path=base_path,
                stage_name="link_selection",
                messages=messages,
                response=content,
                request_id=f"link_selection_{ref_id}"
            )

            # Parse JSON response
            try:
                parsed_json = json.loads(content)
                selected_url = parsed_json.get('selected_url', '')

                # Find the candidate with matching URL
                for candidate in candidates:
                    if candidate.get('url') == selected_url:
                        return candidate

                logger.warning(f"Selected URL '{selected_url}' not found in candidates for ref_id={ref_id}")
                return candidates[0] if candidates else None

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON selection for ref_id={ref_id}: {e}")
                # Try enhanced JSON parsing
                try:
                    parsed_json = _parse_json_from_response(content)
                    selected_url = parsed_json.get('selected_url', '')

                    for candidate in candidates:
                        if candidate.get('url') == selected_url:
                            return candidate

                except Exception as e2:
                    logger.error(f"Enhanced JSON parsing also failed for ref_id={ref_id}: {e2}")

                return candidates[0] if candidates else None

        except Exception as e:
            logger.error(f"LLM selection failed for ref_id={ref_id}: {e}")
            return candidates[0] if candidates else None

    def apply_links(self, html_content: str, selected_links: Dict[str, Dict], base_path: str) -> str:
        """
        Step 4: Apply selected links to HTML content with academic footnotes.
        Auto-reindexes link numbers to create sequential 1,2,3... numbering.

        Returns:
            HTML content with academic footnotes and references section
        """
        logger.info("Applying links to content...")

        # Filter valid links and create reindex mapping in CORRECT ORDER
        valid_links = {}
        reindex_map = {}

        # Sort ref_ids by numeric value to maintain sequential order
        sorted_ref_ids = []
        for ref_id, link_info in selected_links.items():
            if link_info['chosen_url']:
                try:
                    # Convert ref_id to int for proper sorting
                    sorted_ref_ids.append((int(ref_id), ref_id, link_info))
                except ValueError:
                    # If ref_id is not numeric, append at end
                    sorted_ref_ids.append((9999, ref_id, link_info))

        # Sort by numeric value
        sorted_ref_ids.sort(key=lambda x: x[0])

        # Create mapping with sequential indices
        new_index = 1
        for _, ref_id, link_info in sorted_ref_ids:
            valid_links[ref_id] = link_info
            reindex_map[ref_id] = str(new_index)
            new_index += 1

        logger.info(f"Reindexing {len(valid_links)} valid links from {len(selected_links)} total")

        # Replace markers with academic footnotes using new indices
        processed_content = html_content
        references = []

        for old_ref_id, link_info in valid_links.items():
            new_ref_id = reindex_map[old_ref_id]

            # Look for simple markers [1] (preferred) or existing anchor tags
            simple_marker_pattern = f"\\[{old_ref_id}\\]"

            # First try to find and replace simple markers (this is what we expect from the improved insertion)
            marker_matches = re.findall(simple_marker_pattern, processed_content)

            if marker_matches:
                # Create academic footnote anchor with NEW index
                footnote_anchor = f'<a id="cite-{new_ref_id}" href="#ref-{new_ref_id}" rel="nofollow">[{new_ref_id}]</a>'

                # Replace the first occurrence of the simple marker
                processed_content = re.sub(simple_marker_pattern, footnote_anchor, processed_content, count=1)
                logger.debug(f"Replaced simple marker [{old_ref_id}] with footnote anchor [{new_ref_id}]")
            else:
                # Fallback: look for existing anchor tags (for backward compatibility)
                existing_anchor_pattern = f"<a id=['\"]cite-{old_ref_id}['\"] href=['\"]#ref-{old_ref_id}['\"]>\\[{old_ref_id}\\]</a>"
                if re.search(existing_anchor_pattern, processed_content):
                    footnote_anchor = f'<a id="cite-{new_ref_id}" href="#ref-{new_ref_id}" rel="nofollow">[{new_ref_id}]</a>'
                    processed_content = re.sub(existing_anchor_pattern, footnote_anchor, processed_content)
                    logger.debug(f"Replaced existing anchor cite-{old_ref_id} with [{new_ref_id}]")
                else:
                    logger.warning(f"No marker found for ref_id {old_ref_id}, skipping link application")

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

        # Validate final HTML structure
        self._validate_html_structure(processed_content, len(references))

        # Save final content
        self._save_artifact(processed_content, base_path, 'article_with_links.html')

        logger.info(f"Applied {len(references)} sequential academic footnotes to content")
        return processed_content

    def _validate_html_structure(self, html_content: str, expected_links: int) -> None:
        """Validate the final HTML structure for common issues."""
        import re

        # Check for nested anchor tags (common issue)
        nested_anchor_pattern = r'<a[^>]*><a[^>]*>'
        nested_matches = re.findall(nested_anchor_pattern, html_content)
        if nested_matches:
            logger.error(f"Found {len(nested_matches)} nested anchor tags - this indicates marker duplication")
            for match in nested_matches[:3]:  # Show first 3 examples
                logger.error(f"Nested anchor example: {match}")

        # Check for malformed markers
        malformed_pattern = r'\\[\\d+\\](?!<)|<a[^>]*>\\[\\d+\\](?!</a>)'
        malformed_matches = re.findall(malformed_pattern, html_content)
        if malformed_matches:
            logger.warning(f"Found {len(malformed_matches)} potentially malformed markers")

        # Count actual footnote anchors
        footnote_pattern = r'<a id="cite-\\d+" href="#ref-\\d+"[^>]*>\\[\\d+\\]</a>'
        actual_footnotes = len(re.findall(footnote_pattern, html_content))

        if actual_footnotes != expected_links:
            logger.warning(f"Footnote count mismatch: expected {expected_links}, found {actual_footnotes}")

        # Check for reference section
        if expected_links > 0:
            if 'Полезные ссылки' not in html_content:
                logger.error("Missing 'Полезные ссылки' section despite having links")

            ref_pattern = r'<li id="ref-\\d+">'
            ref_count = len(re.findall(ref_pattern, html_content))
            if ref_count != expected_links:
                logger.warning(f"References count mismatch: expected {expected_links}, found {ref_count}")

        logger.debug(f"HTML validation complete: {actual_footnotes} footnotes, structure appears {'valid' if not nested_matches else 'INVALID'}")

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

    def _find_best_insertion_point(self, text: str, anchor_text: str, context_before: str = "", context_after: str = "") -> int:
        """
        Find the best position to insert a marker after anchor_text, avoiding HTML tags.

        Args:
            text: Full HTML content
            anchor_text: The exact text substring to find
            context_before: 10-15 characters before anchor_text for precise localization
            context_after: 10-15 characters after anchor_text for precise localization

        Returns:
            Best character position to insert marker, or -1 if not found
        """
        logger.debug(f"Finding insertion point for anchor_text: '{anchor_text}'")

        # Try to find using full context first (most precise)
        if context_before and context_after:
            search_pattern = context_before + anchor_text + context_after
            pattern_pos = text.find(search_pattern)
            if pattern_pos != -1:
                # Calculate position right after anchor_text
                anchor_start = pattern_pos + len(context_before)
                anchor_end = anchor_start + len(anchor_text)
                return self._adjust_position_to_avoid_tags(text, anchor_end)

        # Fallback to anchor_text with partial context
        if context_before:
            search_pattern = context_before + anchor_text
            pattern_pos = text.find(search_pattern)
            if pattern_pos != -1:
                anchor_start = pattern_pos + len(context_before)
                anchor_end = anchor_start + len(anchor_text)
                return self._adjust_position_to_avoid_tags(text, anchor_end)

        # Last resort: just find anchor_text directly
        anchor_pos = text.find(anchor_text)
        if anchor_pos != -1:
            anchor_end = anchor_pos + len(anchor_text)
            return self._adjust_position_to_avoid_tags(text, anchor_end)

        logger.warning(f"Could not find anchor_text: '{anchor_text}' in content")
        return -1

    def _adjust_position_to_avoid_tags(self, text: str, target_pos: int) -> int:
        """
        Adjust position to avoid placing markers inside HTML tags.

        Args:
            text: Full HTML content
            target_pos: Initial target position

        Returns:
            Adjusted position that's safe for marker insertion
        """
        # Check if we're inside a tag
        tag_start = text.rfind('<', 0, target_pos)
        tag_end = text.rfind('>', 0, target_pos)

        # If we're inside a tag (< comes after >), move to after the closing >
        if tag_start > tag_end:
            next_close = text.find('>', target_pos)
            if next_close != -1:
                target_pos = next_close + 1

        # Look for better insertion points nearby
        # Priority: end of sentence > punctuation > word boundary

        # Search window around target position
        window_start = max(0, target_pos - 20)
        window_end = min(len(text), target_pos + 20)
        window = text[window_start:window_end]

        # Relative position in window
        rel_pos = target_pos - window_start

        # Look for sentence endings first (highest priority)
        sentence_endings = ['. ', '.</p>', '.</h', '.\n']
        for ending in sentence_endings:
            end_pos = window.find(ending, max(0, rel_pos - 10), min(len(window), rel_pos + 10))
            if end_pos != -1:
                return window_start + end_pos + len(ending) - 1

        # Look for punctuation (medium priority)
        punctuation_marks = [', ', '; ', ') ', ' – ', ' — ']
        for punct in punctuation_marks:
            punct_pos = window.find(punct, max(0, rel_pos - 10), min(len(window), rel_pos + 10))
            if punct_pos != -1:
                return window_start + punct_pos + len(punct) - 1

        # Look for word boundaries (lowest priority)
        for i in range(max(0, rel_pos - 5), min(len(window), rel_pos + 5)):
            if i < len(window) and window[i] == ' ' and i > 0 and window[i-1].isalnum():
                return window_start + i

        # If nothing found, return original position
        return target_pos

    def _insert_markers_with_smart_positioning(self, html_content: str, link_plan: List[Dict]) -> str:
        """
        Insert markers into HTML content using smart positioning based on anchor_text.

        Args:
            html_content: Original HTML content
            link_plan: List of link plans with anchor_text and context

        Returns:
            HTML content with markers inserted
        """
        content = html_content
        insertions = []

        logger.info(f"🔧 Starting smart positioning for {len(link_plan)} markers")

        for plan in link_plan:
            ref_id = plan.get('ref_id', '')
            anchor_text = plan.get('anchor_text', '')
            context_before = plan.get('context_before', '')
            context_after = plan.get('context_after', '')

            logger.debug(f"📍 Processing marker [{ref_id}]: anchor='{anchor_text}', before='{context_before}', after='{context_after}'")

            if not anchor_text:
                logger.warning(f"No anchor_text provided for ref_id {ref_id}, skipping")
                continue

            insertion_pos = self._find_best_insertion_point(
                content, anchor_text, context_before, context_after
            )

            if insertion_pos == -1:
                logger.warning(f"❌ Could not find insertion point for marker [{ref_id}]")
                logger.debug(f"   Search pattern: '{context_before}{anchor_text}{context_after}'")
                continue

            logger.debug(f"✅ Found insertion point for marker [{ref_id}] at position {insertion_pos}")

            insertions.append({
                'ref_id': ref_id,
                'position': insertion_pos,
                'marker': f'[{ref_id}]'
            })

        # Sort insertions by position (reverse order to maintain positions)
        insertions.sort(key=lambda x: x['position'], reverse=True)

        # Insert markers from right to left to maintain positions
        for insertion in insertions:
            pos = insertion['position']
            marker = insertion['marker']
            content = content[:pos] + marker + content[pos:]

            logger.debug(f"Inserted {marker} at position {pos}")

        # Save debug information
        debug_info = [
            {
                'ref_id': ins['ref_id'],
                'position': ins['position'],
                'marker': ins['marker']
            }
            for ins in reversed(insertions)  # Reverse to show original order
        ]

        # Store debug info for later saving
        self._debug_insertions = debug_info

        logger.info(f"🎯 Smart positioning complete: {len(insertions)}/{len(link_plan)} markers inserted successfully")

        return content

    def _validate_anchors(self, html_content: str, link_plan: List[Dict]) -> Dict:
        """
        Validate that all anchor_text exist in the HTML content.
        Simplified validation: only checks for anchor_text presence, ignoring strict context matching.

        Args:
            html_content: Original HTML content
            link_plan: List of link plans with anchor_text and context

        Returns:
            Validation report with detailed information
        """
        report = {
            "total_anchors": len(link_plan),
            "valid_anchors": 0,
            "invalid_anchors": 0,
            "validation_details": []
        }

        # Lazy initialization for BeautifulSoup fallback
        clean_text_normalized = None
        bs4_available = None

        for plan in link_plan:
            ref_id = plan.get('ref_id', 'unknown')
            anchor_text = plan.get('anchor_text', '')
            context_before = plan.get('context_before', '')
            context_after = plan.get('context_after', '')

            detail = {
                "ref_id": ref_id,
                "anchor_text": anchor_text,
                "context_before": context_before,
                "context_after": context_after,
                "found": False,
                "position": -1,
                "issues": []
            }

            # Normalize anchor text
            anchor_normalized = ' '.join(anchor_text.split())

            # First try exact match in HTML
            if anchor_text in html_content:
                detail["found"] = True
                detail["position"] = html_content.find(anchor_text)
                report["valid_anchors"] += 1
                logger.debug(f"✅ Anchor [{ref_id}] found in HTML at position {detail['position']}")
            else:
                # Try fallback with BeautifulSoup if available
                if clean_text_normalized is None:
                    # First time we need BS4 - try to initialize
                    if bs4_available is None:
                        try:
                            from bs4 import BeautifulSoup
                            bs4_available = True
                            logger.debug("BeautifulSoup loaded for fallback validation")
                        except ImportError:
                            bs4_available = False
                            logger.debug("BeautifulSoup not available - skipping fallback validation")

                    if bs4_available:
                        try:
                            soup = BeautifulSoup(html_content, 'html.parser')
                            clean_text = soup.get_text()
                            clean_text_normalized = ' '.join(clean_text.split())
                        except Exception as e:
                            logger.warning(f"Failed to create normalized text with BeautifulSoup: {e}")
                            clean_text_normalized = ""
                    else:
                        clean_text_normalized = ""

                # Try normalized text match if we have it
                if clean_text_normalized and anchor_normalized in clean_text_normalized:
                    detail["found"] = True
                    detail["position"] = clean_text_normalized.find(anchor_normalized)
                    report["valid_anchors"] += 1
                    logger.debug(f"✅ Anchor [{ref_id}] found in clean text (normalized) via BS4 fallback")
                else:
                    detail["issues"].append(f"anchor_text '{anchor_text}' not found in HTML or clean text")
                    report["invalid_anchors"] += 1
                    logger.warning(f"❌ Anchor [{ref_id}] validation failed: anchor_text not found")

            report["validation_details"].append(detail)

        logger.info(f"Anchor validation: {report['valid_anchors']}/{report['total_anchors']} valid")
        return report

    def _prepare_html_for_llm(self, html_content: str) -> str:
        """
        Prepare HTML content for LLM by marking elements that should not be used for anchors.
        This helps LLM avoid selecting text inside headers, code blocks, etc.

        Args:
            html_content: Original HTML content

        Returns:
            Marked HTML content
        """
        content = html_content

        # Mark headers to avoid them being selected
        content = content.replace('<h1>', '[HEADER_START]<h1>')
        content = content.replace('</h1>', '</h1>[HEADER_END]')
        content = content.replace('<h2>', '[HEADER_START]<h2>')
        content = content.replace('</h2>', '</h2>[HEADER_END]')
        content = content.replace('<h3>', '[HEADER_START]<h3>')
        content = content.replace('</h3>', '</h3>[HEADER_END]')

        # Mark code blocks to avoid them
        content = content.replace('<code>', '[CODE_START]<code>')
        content = content.replace('</code>', '</code>[CODE_END]')
        content = content.replace('<pre>', '[CODE_START]<pre>')
        content = content.replace('</pre>', '</pre>[CODE_END]')

        # Mark strong and emphasis tags
        content = content.replace('<strong>', '[FORMAT_START]<strong>')
        content = content.replace('</strong>', '</strong>[FORMAT_END]')
        content = content.replace('<em>', '[FORMAT_START]<em>')
        content = content.replace('</em>', '</em>[FORMAT_END]')

        logger.debug("HTML prepared for LLM with special markers")
        return content

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