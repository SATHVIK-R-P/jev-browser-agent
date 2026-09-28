import asyncio
import logging
from typing import Optional, Dict, Any, Tuple
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from backend.browser.page_state import InteractiveElement

logger = logging.getLogger(__name__)

class ActionExecutor:
    """
    Executes browser actions using resilient multi-tier locator resolution:
    1. Robust CSS / ID selectors
    2. Accessible Role & Name locators
    3. DOM JavaScript dispatch
    4. Coordinate-based fallback clicking
    """

    def __init__(self, default_timeout_ms: int = 8000):
        self.default_timeout_ms = default_timeout_ms

    async def navigate(self, page: Page, url: str) -> Tuple[bool, str]:
        try:
            if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("file://"):
                url = f"https://{url}"
            await page.goto(url, wait_until="domcontentloaded", timeout=self.default_timeout_ms * 2)
            await page.wait_for_load_state("networkidle", timeout=3000)
            return True, f"Navigated successfully to {url}"
        except Exception as exc:
            return False, f"Navigation failed to {url}: {exc}"

    async def click(
        self,
        page: Page,
        element: Optional[InteractiveElement] = None,
        selector: Optional[str] = None,
        timeout_ms: Optional[int] = None
    ) -> Tuple[bool, str]:
        t_out = timeout_ms or self.default_timeout_ms

        # Strategy 1: Use specific selector if available
        sel = selector or (element.selector if element else None)
        if sel:
            try:
                locator = page.locator(sel).first
                await locator.scroll_into_view_if_needed(timeout=2000)
                await locator.click(timeout=t_out)
                return True, f"Clicked element with selector '{sel}'"
            except Exception as exc1:
                logger.debug(f"Direct click failed on {sel}: {exc1}. Attempting role/name locator.")

        # Strategy 2: Role and accessible name
        if element and element.role and element.name:
            try:
                loc = page.get_by_role(element.role, name=element.name).first
                await loc.click(timeout=2500)
                return True, f"Clicked via accessible role='{element.role}', name='{element.name}'"
            except Exception:
                pass

        # Strategy 3: JavaScript direct click (bypasses overlays / sticky headers)
        if sel:
            try:
                clicked = await page.evaluate(f"""
                    () => {{
                        const el = document.querySelector("{sel}");
                        if (el) {{
                            el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                            el.click();
                            return true;
                        }}
                        return false;
                    }}
                """)
                if clicked:
                    return True, f"Clicked element via JavaScript dispatch on '{sel}'"
            except Exception:
                pass

        # Strategy 4: Coordinate-based fallback
        if element and element.bounding_box:
            box = element.bounding_box
            if box.get("width", 0) > 0 and box.get("height", 0) > 0:
                try:
                    center_x = box["x"] + (box["width"] / 2)
                    center_y = box["y"] + (box["height"] / 2)
                    await page.mouse.click(center_x, center_y)
                    return True, f"Clicked via coordinate fallback at ({center_x:.0f}, {center_y:.0f})"
                except Exception as exc_coord:
                    return False, f"Coordinate click failed: {exc_coord}"

        return False, f"Could not interact with target element '{sel or (element.id if element else 'unknown')}'"

    async def type_text(
        self,
        page: Page,
        text: str,
        element: Optional[InteractiveElement] = None,
        selector: Optional[str] = None,
        press_enter: bool = True,
        timeout_ms: Optional[int] = None
    ) -> Tuple[bool, str]:
        t_out = timeout_ms or self.default_timeout_ms
        sel = selector or (element.selector if element else None)

        if not sel and element and element.id:
            sel = f"#{element.id}"

        target_locator = None
        if sel:
            target_locator = page.locator(sel).first
        elif element and element.name:
            target_locator = page.get_by_placeholder(element.name).first

        if target_locator:
            try:
                await target_locator.scroll_into_view_if_needed(timeout=2000)
                await target_locator.click(timeout=2000)
                await target_locator.fill(text, timeout=t_out)
                if press_enter:
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(500)
                return True, f"Typed text into '{sel}' and submitted (enter={press_enter})"
            except Exception as exc:
                logger.debug(f"Direct fill failed on {sel}: {exc}. Trying JS value injection.")

        # Fallback via evaluate
        if sel:
            try:
                injected = await page.evaluate(f"""
                    () => {{
                        const el = document.querySelector("{sel}");
                        if (el) {{
                            el.focus();
                            el.value = "{text}";
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                        return false;
                    }}
                """)
                if injected:
                    if press_enter:
                        await page.keyboard.press("Enter")
                    return True, f"Injected text into '{sel}' via JS"
            except Exception as exc_js:
                return False, f"Type text failed: {exc_js}"

        return False, f"Could not find input element to type text into."

    async def scroll(self, page: Page, direction: str = "down", amount: int = 500) -> Tuple[bool, str]:
        try:
            delta = amount if direction.lower() == "down" else -amount
            await page.evaluate(f"window.scrollBy({{ top: {delta}, left: 0, behavior: 'smooth' }});")
            await page.wait_for_timeout(300)
            return True, f"Scrolled {direction} by {amount}px"
        except Exception as exc:
            return False, f"Scroll failed: {exc}"

    async def select_option(self, page: Page, selector: str, value: str) -> Tuple[bool, str]:
        try:
            await page.locator(selector).first.select_option(value=value, timeout=self.default_timeout_ms)
            return True, f"Selected option '{value}' in '{selector}'"
        except Exception as exc:
            return False, f"Select option failed: {exc}"

    async def wait(self, page: Page, ms: int = 1000) -> Tuple[bool, str]:
        try:
            await page.wait_for_timeout(ms)
            return True, f"Waited for {ms}ms"
        except Exception as exc:
            return False, f"Wait failed: {exc}"
