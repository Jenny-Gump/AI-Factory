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
        logger.info(f"Scraping URL: {url_to_scrape}")
        try:
            async with session.post(scrape_url, json=json_data) as response:
                response.raise_for_status()
                scraped_data = await response.json()
                return scraped_data.get('data', {})
        except aiohttp.ClientError as e:
            logger.error(f"Failed to scrape {url_to_scrape}: {e}")
            return {}

    async def scrape_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Scrapes a list of URLs concurrently.
        """
        logger.info(f"Starting to scrape {len(urls)} URLs.")
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
            tasks = [self.scrape_url(session, url) for url in urls]
            results = await asyncio.gather(*tasks)
        
        successful_scrapes = [res for res in results if res]
        logger.info(f"Successfully scraped {len(successful_scrapes)} out of {len(urls)} URLs.")
        return successful_scrapes
