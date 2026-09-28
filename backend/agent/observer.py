from typing import Optional, Dict, Any
from playwright.async_api import Page
from backend.browser.page_observer import PageObserver
from backend.browser.page_state import PageState

class AgentObserver:
    """
    Coordinates page state capture, screenshot formatting, and structured summaries
    for the agent loop.
    """

    def __init__(self, page_observer: Optional[PageObserver] = None):
        self.page_observer = page_observer or PageObserver()

    async def observe_page(
        self,
        page: Page,
        task_id: str,
        step_number: int,
        capture_screenshots: bool = True
    ) -> PageState:
        return await self.page_observer.observe(
            page=page,
            task_id=task_id,
            step_number=step_number,
            capture_screenshot=capture_screenshots
        )
