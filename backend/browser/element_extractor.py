from typing import List, Dict, Any
from playwright.async_api import Page
from backend.browser.page_state import InteractiveElement

# Client-side JavaScript to scan the DOM and extract all interactive elements
ELEMENT_EXTRACTION_SCRIPT = """
() => {
    function getCssSelector(el) {
        if (el.id) {
            return `#${CSS.escape(el.id)}`;
        }
        if (el.getAttribute('data-testid')) {
            return `[data-testid="${CSS.escape(el.getAttribute('data-testid'))}"]`;
        }
        if (el.getAttribute('name')) {
            return `${el.tagName.toLowerCase()}[name="${CSS.escape(el.getAttribute('name'))}"]`;
        }
        if (el.getAttribute('aria-label')) {
            return `[aria-label="${CSS.escape(el.getAttribute('aria-label'))}"]`;
        }
        
        let path = [];
        let curr = el;
        while (curr && curr.nodeType === Node.ELEMENT_NODE) {
            let selector = curr.tagName.toLowerCase();
            if (curr.id) {
                selector = `#${CSS.escape(curr.id)}`;
                path.unshift(selector);
                break;
            } else {
                let sibling = curr;
                let nth = 1;
                while (sibling = sibling.previousElementSibling) {
                    if (sibling.tagName.toLowerCase() === selector) nth++;
                }
                if (nth > 1) selector += `:nth-of-type(${nth})`;
            }
            path.unshift(selector);
            curr = curr.parentElement;
            if (path.length > 5) break;
        }
        return path.join(' > ');
    }

    function isElementVisible(el) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    const interactiveSelectors = [
        'button',
        'a[href]',
        'input',
        'textarea',
        'select',
        '[role="button"]',
        '[role="link"]',
        '[role="searchbox"]',
        '[role="textbox"]',
        '[role="checkbox"]',
        '[role="combobox"]',
        '[role="menuitem"]',
        '[role="tab"]',
        'form',
        '[tabindex="0"]'
    ];

    const rawElements = Array.from(document.querySelectorAll(interactiveSelectors.join(',')));
    
    // Also include elements with pointer cursor if not already in list
    const allElems = document.querySelectorAll('div, span, li, p');
    for (let i = 0; i < Math.min(allElems.length, 300); i++) {
        const el = allElems[i];
        if (window.getComputedStyle(el).cursor === 'pointer' && !rawElements.includes(el)) {
            rawElements.push(el);
        }
    }

    const results = [];
    let count = 1;
    const seenSelectors = new Set();

    for (const el of rawElements) {
        if (!isElementVisible(el)) continue;

        const rect = el.getBoundingClientRect();
        const tagName = el.tagName.toLowerCase();
        let role = el.getAttribute('role') || tagName;
        if (tagName === 'input') {
            role = el.getAttribute('type') || 'text';
        } else if (tagName === 'a') {
            role = 'link';
        }

        const name = (
            el.getAttribute('aria-label') ||
            el.getAttribute('aria-labelledby') ||
            el.getAttribute('title') ||
            el.getAttribute('placeholder') ||
            el.getAttribute('alt') ||
            (el.innerText || '').slice(0, 80).trim() ||
            el.getAttribute('value') ||
            ''
        ).replace(/\\s+/g, ' ').trim();

        const innerText = (el.innerText || '').slice(0, 100).replace(/\\s+/g, ' ').trim();
        const selector = getCssSelector(el);

        // Avoid duplicate redundant container items
        if (seenSelectors.has(selector)) continue;
        seenSelectors.add(selector);

        const attributes = {};
        for (const attr of ['href', 'type', 'name', 'placeholder', 'value', 'aria-label', 'data-testid']) {
            if (el.hasAttribute(attr)) {
                attributes[attr] = el.getAttribute(attr);
            }
        }

        results.push({
            id: `element_${count++}`,
            tag_name: tagName,
            role: role,
            name: name,
            text: innerText,
            selector: selector,
            attributes: attributes,
            bounding_box: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            },
            is_visible: true,
            is_enabled: !el.disabled
        });

        if (count > 75) break; // Keep candidate set bounded and responsive
    }

    return results;
}
"""

class ElementExtractor:
    """
    Scans the current DOM via Playwright page and extracts structured interactive elements.
    """

    async def extract_interactive_elements(self, page: Page) -> List[InteractiveElement]:
        try:
            raw_elements = await page.evaluate(ELEMENT_EXTRACTION_SCRIPT)
            elements: List[InteractiveElement] = []
            for item in raw_elements:
                elements.append(InteractiveElement(**item))
            return elements
        except Exception as exc:
            # Fallback if evaluation failed
            return []
