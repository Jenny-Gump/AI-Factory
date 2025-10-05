import asyncio
import aiohttp
from typing import List, Dict, Any

from src.config import FIRECRAWL_API_KEY, SEARCH_DOMAINS
from src.logger_config import logger

class FirecrawlClient:
    """
    A client to interact with the Firecrawl API v2 using aiohttp for async requests.
    """
    def __init__(self):
        if not FIRECRAWL_API_KEY:
            raise ValueError("FIRECRAWL_API_KEY is not set in the environment variables.")
        self.base_url = "https://api.firecrawl.dev/v2"
        self.headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json",
        }

    async def search(self, topic: str) -> List[Dict[str, Any]]:
        """
        Performs a broad search using the Firecrawl API v2.
        """
        logger.info(f"Starting broad search for topic: '{topic}' using API v2")
        
        # Broad query to get top results, optionally filtered by general domains
        search_query = f'{topic}'
        
        url = f"{self.base_url}/search"
        json_data = {
            "query": search_query,
            "limit": 20 # Get top 20 results
        }
        
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
            try:
                async with session.post(url, json=json_data) as response:
                    response.raise_for_status()
                    search_results = await response.json()
                    results = search_results.get('data', {}).get('web', [])
                    logger.info(f"Found {len(results)} results from Firecrawl search.")
                    return results
            except aiohttp.ClientError as e:
                logger.error(f"An error occurred during Firecrawl search: {e}")
                return []

    async def scrape_url(self, session: aiohttp.ClientSession, url_to_scrape: str) -> Dict[str, Any]:
        """
        Scrapes a single URL using the Firecrawl Scrape API v2 with enhanced content filtering.
        """
        import time
        start_time = time.time()

        scrape_url = f"{self.base_url}/scrape"
        json_data = {
            "url": url_to_scrape,
            "onlyMainContent": True,
            "excludeTags": [
                'nav', 'header', 'footer', 'aside', 'form', 'script', 'style',
                'iframe', 'video', 'audio', 'canvas', 'svg', 'noscript',
                'button', 'input', 'select', 'textarea'
            ],
            "includeTags": [
                'main', 'article', 'section', 'div', 'p', 'h1', 'h2', 'h3',
                'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code'
            ],
            "removeBase64Images": True,
            "blockAds": True
        }

        url_short = url_to_scrape[:80] + '...' if len(url_to_scrape) > 80 else url_to_scrape
        logger.info(f"🔵 Sending Firecrawl request: {url_short}")

        try:
            async with session.post(scrape_url, json=json_data) as response:
                elapsed = time.time() - start_time
                status = response.status

                if status == 200:
                    scraped_data = await response.json()
                    content_size = len(scraped_data.get('data', {}).get('content', ''))
                    logger.info(f"✅ Firecrawl SUCCESS: {url_short} | {status} | {content_size} chars | {elapsed:.1f}s")
                    return scraped_data.get('data', {})
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Firecrawl HTTP {status}: {url_short} | {error_text[:200]} | {elapsed:.1f}s")
                    return {}

        except asyncio.TimeoutError as e:
            elapsed = time.time() - start_time
            logger.error(f"⏰ Firecrawl TIMEOUT: {url_short} | {elapsed:.1f}s", exc_info=True)
            return {}
        except aiohttp.ClientError as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ Firecrawl ERROR: {url_short} | {type(e).__name__}: {e} | {elapsed:.1f}s", exc_info=True)
            return {}
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"💥 Firecrawl UNEXPECTED: {url_short} | {type(e).__name__}: {e} | {elapsed:.1f}s", exc_info=True)
            return {}

    async def batch_scrape_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Scrapes multiple URLs using Firecrawl Batch Scrape API with job polling.
        """
        import time
        import json
        overall_start = time.time()

        logger.info(f"🚀 Using Firecrawl BATCH SCRAPE for {len(urls)} URLs...")
        logger.info(f"📋 First 5 URLs: {[url[:60]+'...' if len(url)>60 else url for url in urls[:5]]}" + (f" ...and {len(urls)-5} more" if len(urls) > 5 else ""))

        batch_url = f"{self.base_url}/batch/scrape"
        json_data = {
            "urls": urls,
            "timeout": 120000,  # 120 seconds per URL (in milliseconds)
            "onlyMainContent": True,
            "excludeTags": [
                'nav', 'header', 'footer', 'aside', 'form', 'script', 'style',
                'iframe', 'video', 'audio', 'canvas', 'svg', 'noscript',
                'button', 'input', 'select', 'textarea'
            ],
            "includeTags": [
                'main', 'article', 'section', 'div', 'p', 'h1', 'h2', 'h3',
                'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code'
            ],
            "removeBase64Images": True,
            "blockAds": True
        }

        try:
            timeout = aiohttp.ClientTimeout(total=None, sock_read=900)  # 15 min read timeout
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                # Step 1: Start batch scrape job
                logger.info(f"⚡ Starting batch scrape job...")
                async with session.post(batch_url, json=json_data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"❌ Batch start HTTP {response.status}: {error_text[:300]}")
                        logger.warning(f"⚠️ Falling back to individual URL scraping...")
                        return await self._fallback_individual_scrape(urls)

                    job_response = await response.json()
                    logger.info(f"📦 Job start response keys: {list(job_response.keys())}")
                    logger.info(f"📦 Job start response: {json.dumps(job_response)[:500]}")

                    # Extract job info
                    job_id = job_response.get('id')
                    status_url = job_response.get('url')

                    if not job_id or not status_url:
                        logger.error(f"❌ No job ID or status URL in response!")
                        logger.warning(f"⚠️ Falling back to individual URL scraping...")
                        return await self._fallback_individual_scrape(urls)

                    logger.info(f"✅ Batch job started | ID: {job_id}")
                    logger.info(f"📍 Status URL: {status_url}")

                # Step 2: Poll job status
                poll_interval = 5  # seconds between polls
                max_wait_time = 900  # 15 minutes max
                poll_count = 0

                while True:
                    poll_count += 1
                    elapsed = time.time() - overall_start

                    if elapsed > max_wait_time:
                        logger.error(f"⏰ Batch job timeout after {elapsed:.1f}s")
                        logger.warning(f"⚠️ Falling back to individual URL scraping...")
                        return await self._fallback_individual_scrape(urls)

                    # Wait before polling (except first time)
                    if poll_count > 1:
                        await asyncio.sleep(poll_interval)

                    # Poll status
                    logger.info(f"🔄 Polling job status (attempt #{poll_count}, {elapsed:.1f}s elapsed)...")
                    async with session.get(status_url) as status_response:
                        if status_response.status != 200:
                            error_text = await status_response.text()
                            logger.error(f"❌ Status check HTTP {status_response.status}: {error_text[:200]}")
                            continue

                        status_data = await status_response.json()
                        logger.info(f"📊 Status response keys: {list(status_data.keys())}")

                        job_status = status_data.get('status')
                        completed = status_data.get('completed', 0)
                        total = status_data.get('total', len(urls))

                        logger.info(f"📈 Status: {job_status} | Progress: {completed}/{total}")

                        # Check if completed
                        if job_status == 'completed':
                            logger.info(f"✅ Batch job COMPLETED | Total time: {elapsed:.1f}s")

                            # Extract results
                            data = status_data.get('data', [])
                            logger.info(f"📦 Data field type: {type(data)} | Length: {len(data) if isinstance(data, list) else 'N/A'}")

                            if not isinstance(data, list):
                                logger.error(f"❌ Data field is not a list! Type: {type(data)}")
                                logger.warning(f"⚠️ Falling back to individual URL scraping...")
                                return await self._fallback_individual_scrape(urls)

                            # Process results
                            scraped_data = []

                            # Log first result structure for debugging
                            if len(data) > 0:
                                logger.info(f"📄 First result full structure: {json.dumps(data[0], indent=2)[:1000]}")

                            for i, result in enumerate(data):
                                logger.info(f"📄 Result {i+1} keys: {list(result.keys()) if isinstance(result, dict) else 'NOT_DICT'}")

                                if isinstance(result, dict):
                                    # Batch scrape returns results with 'markdown' and 'metadata' fields
                                    if 'markdown' in result:
                                        scraped_data.append(result)
                                    elif 'metadata' in result:
                                        # Even if no markdown, still include metadata-only results
                                        scraped_data.append(result)
                                    else:
                                        logger.warning(f"⚠️ Result {i+1} has unexpected structure: {list(result.keys())}")

                            logger.info(f"✅ BATCH SCRAPE COMPLETE: {len(scraped_data)}/{len(urls)} URLs extracted | {elapsed:.1f}s")
                            return scraped_data

                        elif job_status == 'failed':
                            logger.error(f"❌ Batch job FAILED")
                            logger.error(f"📦 Failed response: {json.dumps(status_data)[:500]}")
                            logger.warning(f"⚠️ Falling back to individual URL scraping...")
                            return await self._fallback_individual_scrape(urls)

                        elif job_status in ['scraping', 'processing', None]:
                            # Still working, continue polling
                            continue
                        else:
                            logger.warning(f"⚠️ Unknown status: {job_status}, continuing to poll...")
                            continue

        except Exception as e:
            elapsed = time.time() - overall_start
            logger.error(f"💥 Batch scrape failed: {type(e).__name__}: {e} | {elapsed:.1f}s", exc_info=True)
            logger.warning(f"⚠️ Falling back to individual URL scraping...")
            return await self._fallback_individual_scrape(urls)

    async def _fallback_individual_scrape(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Fallback method: scrape URLs individually if batch fails"""
        import time
        overall_start = time.time()

        logger.info(f"🔄 FALLBACK: Scraping {len(urls)} URLs individually...")

        timeout = aiohttp.ClientTimeout(total=None, sock_read=120)  # 120s per URL
        async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
            tasks = [self.scrape_url(session, url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_scrapes = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ URL {i+1} failed: {type(result).__name__}: {result}")
            elif result:
                successful_scrapes.append(result)

        elapsed = time.time() - overall_start
        logger.info(f"📊 FALLBACK SUMMARY: {len(successful_scrapes)}/{len(urls)} successful | {elapsed:.1f}s")

        return successful_scrapes

    async def scrape_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Main entry point: tries batch scrape first, falls back to individual if needed.
        """
        return await self.batch_scrape_urls(urls)
