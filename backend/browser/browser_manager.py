import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages Playwright Chromium lifecycle, browser contexts, and page navigation.
    """

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 800,
        timeout_ms: int = 30000
    ):
        self.headless = headless
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.timeout_ms = timeout_ms
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()

    async def start(self) -> Page:
        """Launches Chromium browser and returns an active page."""
        async with self._lock:
            if self._page and not self._page.is_closed():
                return self._page

            logger.info(f"Launching Playwright Chromium (headless={self.headless})...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )

            self._context = await self._browser.new_context(
                viewport=self.viewport,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="en-US"
            )
            self._context.set_default_timeout(self.timeout_ms)
            self._page = await self._context.new_page()
            logger.info("Chromium browser successfully initialized.")
            return self._page

    async def get_page(self) -> Page:
        if not self._page or self._page.is_closed():
            return await self.start()
        return self._page

    async def stop(self):
        """Closes browser context and Playwright instance cleanly."""
        async with self._lock:
            try:
                if self._page and not self._page.is_closed():
                    await self._page.close()
                if self._context:
                    await self._context.close()
                if self._browser:
                    await self._browser.close()
                if self._playwright:
                    await self._playwright.stop()
                logger.info("Chromium browser terminated cleanly.")
            except Exception as exc:
                logger.warning(f"Error closing browser: {exc}")
            finally:
                self._page = None
                self._context = None
                self._browser = None
                self._playwright = None
