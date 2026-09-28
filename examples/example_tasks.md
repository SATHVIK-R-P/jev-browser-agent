# JEV Browser Agent — Task Examples & Evaluation Guide

This guide details the standard benchmark tasks for validating autonomous web task execution with JEV System-One bounded decisions, confidence routing, and human safety approval.

---

## Example 1: Wikipedia Knowledge Retrieval

**Task Prompt:**
```text
Open Wikipedia and search for artificial intelligence.
```

**Workflow:**
1. Agent initializes Chromium and navigates to `https://www.wikipedia.org`.
2. Inspects DOM elements, identifies search input (`#searchInput` / `element_N`).
3. Candidate generator produces `TYPE` and `CLICK` actions.
4. JEV selects `TYPE 'artificial intelligence' into search input` (Confidence: ~96.3%).
5. Executes search submit.
6. Verifies destination article `https://en.wikipedia.org/wiki/Artificial_intelligence`.
7. Concludes task with verified state summary.

---

## Example 2: Search Engine Discovery

**Task Prompt:**
```text
Open a search engine and search for Python Playwright.
```

**Workflow:**
1. Navigates to `https://duckduckgo.com`.
2. Identifies search query field and enters `Python Playwright`.
3. Submits query and analyzes search result snippets.
4. JEV scores candidate links and selects the official Playwright Python documentation link.
5. Verifies transition to search results.

---

## Example 3: Site Navigation & Contact Discovery

**Task Prompt:**
```text
Open a website and find the contact page.
```

**Workflow:**
1. Navigates to target website.
2. Element extractor identifies navigation bar links, footer links, and buttons.
3. JEV scores candidate actions targeting 'Contact', 'Get in Touch', or 'Support'.
4. Clicks the highest-confidence link.
5. Verifies contact information or contact form.

---

## Example 4: Documentation Lookup

**Task Prompt:**
```text
Find the official documentation page for FastAPI.
```

**Workflow:**
1. Initiates query for FastAPI documentation.
2. Identifies and clicks `https://fastapi.tiangolo.com`.
3. Verifies official tutorial and interactive documentation page.
4. Concludes successfully.

---

## Example 5: Bounded Shopping Exploration with Price Guardrail

**Task Prompt:**
```text
Search a shopping website for laptops under ₹50000 and open a matching product.
```

**Workflow:**
1. Navigates to product portal.
2. Inputs `laptops under 50000`.
3. Applies sorting/filter for lowest price or price range.
4. Opens the cheapest matching laptop product details.
5. **Safety Gate:** The agent never clicks 'Buy Now' or 'Add to Cart' automatically. If a purchase button is detected in candidates, it is classified as `HIGH` risk and paused for Human Confirmation.
