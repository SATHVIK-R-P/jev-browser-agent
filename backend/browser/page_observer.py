import base64
import os
from pathlib import Path
from typing import Optional
from playwright.async_api import Page
from backend.browser.page_state import PageState
from backend.browser.element_extractor import ElementExtractor

class PageObserver:
    """
    Inspects current page state: URL, title, visible text, interactive elements,
    and captures screenshot for live dashboard visualization.
    """

    def __init__(self, element_extractor: Optional[ElementExtractor] = None, screenshots_dir: str = "data/screenshots"):
        self.extractor = element_extractor or ElementExtractor()
        self.screenshots_dir = Path(screenshots_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    async def observe(
        self,
        page: Page,
        task_id: Optional[str] = None,
        step_number: Optional[int] = None,
        capture_screenshot: bool = True
    ) -> PageState:
        url = page.url
        title = await page.title()

        # Extract visible text summary
        try:
            visible_text = await page.evaluate(
                "() => (document.body ? document.body.innerText.slice(0, 800).replace(/\\s+/g, ' ').trim() : '')"
            )
        except Exception:
            visible_text = ""

        # Extract interactive elements
        elements = await self.extractor.extract_interactive_elements(page)

        screenshot_b64: Optional[str] = None
        if capture_screenshot:
            try:
                # Capture JPEG with moderate quality to optimize live stream bandwidth
                screenshot_bytes = await page.screenshot(type="jpeg", quality=75)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

                if task_id and step_number is not None:
                    file_path = self.screenshots_dir / f"{task_id}_step_{step_number}.jpg"
                    file_path.write_bytes(screenshot_bytes)
            except Exception:
                screenshot_b64 = None

        return PageState(
            url=url,
            title=title or "Untitled Page",
            elements=elements,
            text_summary=visible_text,
            screenshot_base64=screenshot_b64
        )
