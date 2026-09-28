import pytest
import asyncio
import os
import tempfile
from pathlib import Path

from backend.agent.planner import Planner
from backend.agent.candidate_generator import CandidateGenerator
from backend.agent.verifier import Verifier
from backend.agent.agent import BrowserAgent
from backend.agent.decision_manager import DecisionManager
from backend.browser.browser_manager import BrowserManager
from backend.browser.page_observer import PageObserver
from backend.browser.element_extractor import ElementExtractor
from backend.browser.page_state import PageState, InteractiveElement
from backend.decision_engine.decision_models import (
    CandidateAction,
    ActionType,
    DecisionResult,
    RiskLevel
)
from backend.decision_engine.confidence import ConfidenceEvaluator
from backend.decision_engine.decision_router import DecisionRouter
from backend.decision_engine.jev_client import MockJEVClient
from backend.decision_engine.fallback_llm import MockLLMFallback
from backend.safety.risk_classifier import RiskClassifier
from backend.safety.permission_manager import PermissionManager
from backend.safety.confirmation_manager import ConfirmationManager
from backend.database.database import Database

def test_planner_subgoals():
    # Wikipedia plan
    p1 = Planner.create_plan("Open Wikipedia and search for artificial intelligence.")
    assert "wikipedia.org" in p1.initial_url
    assert p1.search_query == "artificial intelligence"
    assert len(p1.subgoals) >= 4

    # Search engine plan
    p2 = Planner.create_plan("Open a search engine and search for Python Playwright.")
    assert "duckduckgo.com" in p2.initial_url
    assert "Python Playwright" in p2.search_query

    # Shopping plan
    p3 = Planner.create_plan("Search a shopping website for laptops under ₹50000 and open a matching product.")
    assert "laptop" in p3.search_query

def test_candidate_generator():
    mock_state = PageState(
        url="https://www.example.com",
        title="Example Shopping Portal",
        elements=[
            InteractiveElement(
                id="element_1",
                tag_name="input",
                role="searchbox",
                name="Search Products",
                text="",
                selector="#search-input",
                attributes={"placeholder": "Search..."}
            ),
            InteractiveElement(
                id="element_2",
                tag_name="button",
                role="button",
                name="Search",
                text="Search",
                selector="#search-btn"
            ),
            InteractiveElement(
                id="element_3",
                tag_name="a",
                role="link",
                name="Laptops Under ₹50,000",
                text="Laptops Under ₹50,000",
                selector="#filter-cheap"
            )
        ]
    )

    candidates = CandidateGenerator.generate_candidates(
        page_state=mock_state,
        task_goal="Search for laptops under ₹50000",
        current_subgoal="Enter search query",
        search_query="laptops"
    )

    assert len(candidates) >= 2
    types = [c.action_type for c in candidates]
    assert ActionType.TYPE in types
    assert ActionType.CLICK in types

def test_verifier_action_effect():
    pre = PageState(url="https://example.com/search", title="Search", elements=[])
    post = PageState(url="https://example.com/item/123", title="Budget Laptop Under 50000", text_summary="Laptop specifications ₹42,000", elements=[])

    dec = DecisionResult(
        decision="click",
        target_id="element_3",
        confidence=0.95,
        reason="Click product result",
        provider="mock-jev",
        risk_level=RiskLevel.LOW
    )

    ok, msg, completed = Verifier.verify_action_effect(pre, post, dec, "Search a shopping website for laptops under ₹50000 and open a matching product.")
    assert ok is True
    assert "Budget Laptop" in msg
    assert completed is True

@pytest.mark.asyncio
async def test_agent_max_steps_stop(tmp_path):
    db_file = tmp_path / "test_agent.db"
    db = Database(db_path=str(db_file))
    await db.init_db()

    jev = MockJEVClient(latency_simulate=0.0)
    llm = MockLLMFallback()
    router = DecisionRouter(jev, llm)
    cm = ConfirmationManager()
    pm = PermissionManager()
    dm = DecisionManager(router, cm, pm, db)
    bm = BrowserManager(headless=True)

    agent = BrowserAgent(
        task_id="task_max_steps_test",
        prompt="Open Wikipedia and search for test.",
        browser_manager=bm,
        decision_manager=dm,
        db=db,
        max_steps=2,  # Set very low max_steps to test termination
        action_delay_ms=0,
        capture_screenshots=False
    )

    try:
        final_state = await agent.run()
        assert final_state.current_step <= 2
        assert final_state.status.value in ["COMPLETED", "RUNNING"]
    finally:
        await bm.stop()

@pytest.mark.asyncio
async def test_playwright_local_html_integration(tmp_path):
    """
    Playwright integration test running Chromium against a local HTML page.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Local Test Store</title></head>
    <body>
        <h1>Tech Mart</h1>
        <input id="search-input" name="search" placeholder="Search laptops" value="" />
        <button id="search-btn" role="button">Search</button>
        <div id="results">
            <a id="laptop-link" href="#laptop-details" role="link">Lenovo ThinkPad Laptop - ₹42,000</a>
        </div>
        <script>
            document.getElementById('search-btn').onclick = function() {
                document.getElementById('search-input').value = 'laptops';
                document.title = 'Search Results for Laptops';
            };
        </script>
    </body>
    </html>
    """

    test_file = tmp_path / "test_store.html"
    test_file.write_text(html_content, encoding="utf-8")
    local_url = test_file.as_uri()

    bm = BrowserManager(headless=True)
    try:
        page = await bm.start()
        await page.goto(local_url)

        # 1. Test DOM observation & element extraction
        observer = PageObserver()
        state = await observer.observe(page, capture_screenshot=True)

        assert state.title == "Local Test Store"
        assert len(state.elements) >= 3
        assert state.screenshot_base64 is not None

        # Verify element IDs are stable (element_1, element_2, ...)
        ids = [el.id for el in state.elements]
        assert "element_1" in ids
        assert "element_2" in ids

        # 2. Test candidate generation
        candidates = CandidateGenerator.generate_candidates(
            page_state=state,
            task_goal="Search for laptops under ₹50000",
            search_query="laptops"
        )
        assert len(candidates) >= 2

        # 3. Test JEV choice decision
        jev = MockJEVClient(latency_simulate=0.0)
        from backend.decision_engine.decision_models import DecisionRequest
        req = DecisionRequest(
            task_id="t_int",
            step_number=1,
            task_goal="Search for laptops under ₹50000",
            page_url=state.url,
            page_title=state.title,
            candidates=candidates
        )
        dec = await jev.decide_choice(req)
        assert dec.confidence >= 0.85
        assert dec.decision in [ActionType.TYPE.value, ActionType.CLICK.value]

        # 4. Test action execution (click search button)
        from backend.browser.action_executor import ActionExecutor
        executor = ActionExecutor()
        btn_elem = next(el for el in state.elements if el.tag_name == "button")
        clicked, msg = await executor.click(page, element=btn_elem)
        assert clicked is True

        # Check page updated
        new_title = await page.title()
        assert new_title == "Search Results for Laptops"

    finally:
        await bm.stop()
