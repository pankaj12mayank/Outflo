"""
Outflo - Safe Scraping Engine Architecture
Production-grade scraping with ethical practices
"""

from typing import Any, List

from .base import BaseScraper, ScrapeResult, ScrapeStatus, ScrapeSource, SafetyConfig
from .google_maps import GoogleMapsScraper
from .website import WebsiteCrawler
from .linkedin import LinkedInEnricher
from .csv_importer import CSVImporter
from .job_manager import JobManager, JobType, JobPriority
from .safety import SafetyManager, RateLimiter, UserAgentRotator
from .config import DEFAULT_SAFETY_CONFIG

__all__ = [
    "BaseScraper",
    "ScrapeResult",
    "ScrapeStatus",
    "ScrapeSource",
    "SafetyConfig",
    "DEFAULT_SAFETY_CONFIG",
    "GoogleMapsScraper",
    "WebsiteCrawler",
    "LinkedInEnricher",
    "CSVImporter",
    "JobManager",
    "JobType",
    "JobPriority",
    "SafetyManager",
    "RateLimiter",
    "UserAgentRotator",
    "get_scraping_service",
]

_scraping_service = None

def get_scraping_service():
    global _scraping_service
    if _scraping_service is None:
        _scraping_service = ScrapingService()
    return _scraping_service


class ScrapingService:
    def __init__(self):
        self.safety = SafetyManager()
        self.rate_limiter = RateLimiter()
        self.ua_rotator = UserAgentRotator()

    async def crawl_website(self, url: str, crawl_contact_pages: bool = True) -> Any:
        crawler = WebsiteCrawler(safety_config=DEFAULT_SAFETY_CONFIG)
        await crawler.initialize()
        try:
            return await crawler.scrape(url)
        finally:
            await crawler.cleanup()

    async def search_google_maps(self, keyword: str, location: str = "", limit: int = 20) -> List[Any]:
        scraper = GoogleMapsScraper(safety_config=DEFAULT_SAFETY_CONFIG)
        await scraper.initialize()
        try:
            return await scraper.search(keyword, location, limit=limit)
        finally:
            await scraper.cleanup()

    async def scrape_google_maps_place(self, url: str) -> Any:
        scraper = GoogleMapsScraper(safety_config=DEFAULT_SAFETY_CONFIG)
        await scraper.initialize()
        try:
            return await scraper.scrape(url)
        finally:
            await scraper.cleanup()

    async def enrich_linkedin(self, linkedin_url: str) -> Any:
        enricher = LinkedInEnricher(safety_config=DEFAULT_SAFETY_CONFIG)
        await enricher.initialize()
        try:
            return await enricher.enrich(linkedin_url)
        finally:
            await enricher.cleanup()