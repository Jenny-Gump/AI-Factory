import requests
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from src.config import FIRECRAWL_API_KEY, SEARCH_DOMAINS, CONCURRENT_REQUESTS
from src.logger_config import logger

class FirecrawlClient:
    """
    A client to interact with the Firecrawl API v2 using requests for sync requests.
    """
    def __init__(self):
        if not FIRECRAWL_API_KEY:
            raise ValueError("FIRECRAWL_API_KEY is not set in the environment variables.")
        self.base_url = "https://api.firecrawl.dev/v2"
        self.headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json",
        }

    def search(self, topic: str) -> List[Dict[str, Any]]:
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

        try:
            response = requests.post(url, json=json_data, headers=self.headers, timeout=300)
            response.raise_for_status()
            search_results = response.json()
            results = search_results.get('data', {}).get('web', [])
            logger.info(f"Found {len(results)} results from Firecrawl search.")
            return results
        except requests.RequestException as e:
            logger.error(f"An error occurred during Firecrawl search: {e}")
            return []

    def scrape_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Scrapes multiple URLs using the Firecrawl Scrape API v2 with concurrent processing.
        """
        logger.info(f"Starting to scrape {len(urls)} URLs concurrently...")

        results = []
        max_workers = min(CONCURRENT_REQUESTS, len(urls))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all scraping tasks
            future_to_url = {executor.submit(self._scrape_single_url, url): url for url in urls}

            # Process completed tasks as they finish
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result:  # Only add non-empty results
                        results.append(result)
                except Exception as e:
                    logger.error(f"❌ Failed to scrape {url}: {e}")

        # Log summary
        successful_scrapes = [r for r in results if r]
        logger.info(f"Scraping completed: {len(successful_scrapes)}/{len(urls)} URLs successful")

        return results

    def _scrape_single_url(self, url: str) -> Dict[str, Any]:
        """
        Scrapes a single URL using the Firecrawl Scrape API v2 with retry logic.
        """
        scrape_url = f"{self.base_url}/scrape"
        json_data = {
            "url": url,
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
        logger.info(f"Scraping URL: {url}")

        # Retry logic for API reliability
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = requests.post(scrape_url, json=json_data, headers=self.headers, timeout=60)
                if response.status_code == 200:
                    response_json = response.json()
                    content_data = response_json.get('data', {})

                    logger.info(f"✅ Successfully scraped: {url[:50]}... (Length: {len(content_data.get('content', ''))} characters)")
                    return content_data
                elif response.status_code == 502 and attempt < max_retries - 1:
                    logger.warning(f"🔄 502 error for {url}, retrying in 5s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(5)
                    continue
                else:
                    logger.error(f"❌ Failed to scrape {url}: HTTP {response.status_code}")
                    return {}
            except requests.Timeout as e:
                if attempt < max_retries - 1:
                    logger.warning(f"🔄 Timeout for {url}, retrying (attempt {attempt + 1}/{max_retries})")
                    time.sleep(3)
                    continue
                else:
                    logger.error(f"❌ Final timeout for {url}: {e}")
                    return {}
            except requests.RequestException as e:
                logger.error(f"❌ Failed to scrape {url}: {e}")
                return {}

        return {}