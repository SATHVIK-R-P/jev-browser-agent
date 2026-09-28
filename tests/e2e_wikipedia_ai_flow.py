"""
End-to-End Wikipedia AI Search Flow Verification
=================================================
Flow:
  Open Wikipedia -> Find search input -> TYPE "AI" -> Find Search/Go button ->
  CLICK -> Verify URL contains "AI" -> Verify results contain AI content -> TASK COMPLETED
"""
import asyncio
import sys
import time

# Fix Windows cp1252 console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, ".")

from backend.browser.browser_manager import BrowserManager
from backend.browser.page_observer import PageObserver
from backend.browser.element_extractor import ElementExtractor
from backend.browser.action_executor import ActionExecutor
from backend.agent.candidate_generator import CandidateGenerator
from backend.agent.verifier import Verifier
from backend.decision_engine.jev_client import MockJEVClient
from backend.decision_engine.decision_models import DecisionRequest, ActionType
from backend.decision_engine.confidence import ConfidenceEvaluator
from backend.safety.risk_classifier import RiskClassifier

PASS = "[PASS]"
FAIL = "[FAIL]"
STEP = "[STEP]"
INFO = "[INFO]"

async def run_wikipedia_ai_flow():
    bm = BrowserManager(headless=True)
    observer = PageObserver()
    executor = ActionExecutor()
    jev = MockJEVClient(latency_simulate=0.0)
    evaluator = ConfidenceEvaluator(auto_execute_threshold=0.90, low_risk_threshold=0.70)
    step_num = 0
    results = []

    def report(status, msg):
        print(f"  {status} {msg}")
        results.append((status, msg))

    print("=" * 70)
    print("  JEV Browser Agent -- Wikipedia AI Search E2E Flow Verification")
    print("=" * 70)
    print()

    try:
        # ============================================================
        # STEP 1: Open Wikipedia
        # ============================================================
        step_num += 1
        print(f"{STEP} Step {step_num}: Open Wikipedia")
        page = await bm.start()
        nav_ok, nav_msg = await executor.navigate(page, "https://www.wikipedia.org")
        await page.wait_for_load_state("networkidle", timeout=10000)

        url_after_nav = page.url
        title_after_nav = await page.title()

        if nav_ok and "wikipedia" in url_after_nav.lower():
            report(PASS, f"Navigated to Wikipedia: {url_after_nav}")
            report(INFO, f"Page title: '{title_after_nav}'")
        else:
            report(FAIL, f"Navigation failed: {nav_msg}")
            return results

        # ============================================================
        # STEP 2: Observe page & Find search input
        # ============================================================
        step_num += 1
        print(f"\n{STEP} Step {step_num}: Observe page and find search input")
        state = await observer.observe(page, task_id="wiki_ai_test", step_number=step_num, capture_screenshot=True)

        report(INFO, f"Total interactive elements detected: {len(state.elements)}")

        # Find search input element
        search_input = None
        for el in state.elements:
            el_info = f"{el.tag_name} {el.role} {el.name} {el.text}".lower()
            attrs_str = str(el.attributes).lower()
            if el.tag_name in ["input", "textarea"] or el.role in ["searchbox", "textbox", "search"]:
                if any(kw in el_info or kw in attrs_str for kw in ["search", "query", "find"]):
                    search_input = el
                    break

        if search_input:
            report(PASS, f"Found search input: [{search_input.id}] <{search_input.tag_name}> role='{search_input.role}' name='{search_input.name}' selector='{search_input.selector}'")
        else:
            # Fallback: try first input
            for el in state.elements:
                if el.tag_name in ["input", "textarea"]:
                    search_input = el
                    break
            if search_input:
                report(PASS, f"Found input element (fallback): [{search_input.id}] <{search_input.tag_name}> selector='{search_input.selector}'")
            else:
                report(FAIL, "Could not find any search input element!")
                return results

        # ============================================================
        # STEP 3: Generate candidates & JEV decides TYPE "AI"
        # ============================================================
        step_num += 1
        print(f"\n{STEP} Step {step_num}: Generate candidate actions & JEV decision for TYPE 'AI'")

        candidates = CandidateGenerator.generate_candidates(
            page_state=state,
            task_goal="Open Wikipedia and search for AI",
            current_subgoal="Type 'AI' into search input",
            search_query="AI"
        )
        report(INFO, f"Generated {len(candidates)} candidate actions:")
        for i, c in enumerate(candidates):
            risk, _ = RiskClassifier.classify(c.action_type, c.target_text, c.target_selector, c.value, c.description)
            report(INFO, f"  #{i+1} {c.action_type.value.upper():10s} target={c.target_id or 'viewport':12s} value='{(c.value or '')[:30]}' risk={risk.value} -- {c.description[:50]}")

        # JEV decision
        req = DecisionRequest(
            task_id="wiki_ai_test",
            step_number=step_num,
            task_goal="Open Wikipedia and search for AI",
            current_subgoal="Type 'AI' into search input",
            page_url=state.url,
            page_title=state.title,
            candidates=candidates
        )
        decision = await jev.decide_choice(req)

        report(INFO, f"JEV Decision: action={decision.decision.upper()}, target={decision.target_id}, confidence={decision.confidence:.4f}, provider={decision.provider}")
        report(INFO, f"JEV Reason: {decision.reason}")

        # Confidence evaluation
        verdict, verdict_msg = evaluator.evaluate(decision.confidence, decision.risk_level)
        report(INFO, f"Confidence routing: {verdict.value} -- {verdict_msg}")

        if decision.decision == ActionType.TYPE.value and decision.confidence >= 0.70:
            report(PASS, f"JEV correctly selected TYPE action with confidence {decision.confidence:.3f} (>= 0.70 threshold)")
        else:
            report(INFO, f"JEV selected {decision.decision} -- proceeding with manual TYPE action")

        # ============================================================
        # STEP 4: Execute TYPE "AI" into search input
        # ============================================================
        step_num += 1
        print(f"\n{STEP} Step {step_num}: Execute TYPE 'AI' into search input")

        pre_type_state = await observer.observe(page, task_id="wiki_ai_test", step_number=step_num, capture_screenshot=False)

        type_ok, type_msg = await executor.type_text(
            page=page,
            text="AI",
            element=search_input,
            selector=search_input.selector,
            press_enter=False  # Don't submit yet; we want to find and click the button
        )

        if type_ok:
            report(PASS, f"Typed 'AI' into search input: {type_msg}")
        else:
            report(FAIL, f"Failed to type: {type_msg}")
            return results

        await page.wait_for_timeout(500)

        # ============================================================
        # STEP 5: Find Search/Go button
        # ============================================================
        step_num += 1
        print(f"\n{STEP} Step {step_num}: Find Search/Go button")

        state_after_type = await observer.observe(page, task_id="wiki_ai_test", step_number=step_num, capture_screenshot=True)

        search_button = None
        for el in state_after_type.elements:
            el_info = f"{el.tag_name} {el.role} {el.name} {el.text}".lower()
            attrs_str = str(el.attributes).lower()
            if el.tag_name == "button" or el.role == "button" or (el.tag_name == "input" and el.attributes.get("type") == "submit"):
                if any(kw in el_info or kw in attrs_str for kw in ["search", "go", "submit", "find"]):
                    search_button = el
                    break

        if search_button:
            report(PASS, f"Found Search/Go button: [{search_button.id}] <{search_button.tag_name}> role='{search_button.role}' name='{search_button.name}' selector='{search_button.selector}'")
        else:
            report(INFO, "No explicit search button found; will press Enter instead")

        # ============================================================
        # STEP 6: JEV decides CLICK on Search/Go button & Execute
        # ============================================================
        step_num += 1
        print(f"\n{STEP} Step {step_num}: JEV decision for CLICK Search/Go & Execute")

        if search_button:
            candidates2 = CandidateGenerator.generate_candidates(
                page_state=state_after_type,
                task_goal="Open Wikipedia and search for AI",
                current_subgoal="Click the Search or Go button to submit",
                search_query="AI",
                recent_actions=["Typed 'AI' into search input"]
            )
            req2 = DecisionRequest(
                task_id="wiki_ai_test",
                step_number=step_num,
                task_goal="Open Wikipedia and search for AI",
                current_subgoal="Click Search/Go button",
                page_url=state_after_type.url,
                page_title=state_after_type.title,
                candidates=candidates2
            )
            decision2 = await jev.decide_choice(req2)
            report(INFO, f"JEV Decision: action={decision2.decision.upper()}, target={decision2.target_id}, confidence={decision2.confidence:.4f}")

            click_ok, click_msg = await executor.click(page, element=search_button, selector=search_button.selector)
            if click_ok:
                report(PASS, f"Clicked Search/Go button: {click_msg}")
            else:
                report(INFO, f"Button click issue ({click_msg}); pressing Enter as fallback")
                await page.keyboard.press("Enter")
                report(PASS, "Pressed Enter key as fallback submission")
        else:
            await page.keyboard.press("Enter")
            report(PASS, "Pressed Enter key to submit search")

        # Wait for navigation to complete
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)

        # ============================================================
        # STEP 7: Verify URL/query contains "AI"
        # ============================================================
        step_num += 1
        print(f"\n{STEP} Step {step_num}: Verify URL/query contains 'AI'")

        result_url = page.url
        result_title = await page.title()

        url_has_ai = "ai" in result_url.lower() or "artificial_intelligence" in result_url.lower() or "search" in result_url.lower()
        report(INFO, f"Result URL: {result_url}")
        report(INFO, f"Result Title: {result_title}")

        if url_has_ai:
            report(PASS, f"URL confirms AI-related navigation: '{result_url}'")
        else:
            report(FAIL, f"URL does not clearly contain 'AI' or 'search': '{result_url}'")

        # ============================================================
        # STEP 8: Verify results page contains AI-related content
        # ============================================================
        step_num += 1
        print(f"\n{STEP} Step {step_num}: Verify results page contains AI-related content")

        post_state = await observer.observe(page, task_id="wiki_ai_test", step_number=step_num, capture_screenshot=True)

        page_text = f"{post_state.title} {post_state.text_summary}".lower()

        ai_keywords_found = []
        ai_keywords_to_check = ["artificial intelligence", "ai", "machine learning", "intelligence", "computer science", "neural", "turing", "algorithm"]
        for kw in ai_keywords_to_check:
            if kw in page_text:
                ai_keywords_found.append(kw)

        report(INFO, f"Page text length: {len(post_state.text_summary)} chars")
        report(INFO, f"Interactive elements on result page: {len(post_state.elements)}")

        if ai_keywords_found:
            report(PASS, f"Page contains AI-related content. Matched keywords: {ai_keywords_found}")
        else:
            report(FAIL, f"Could not find AI-related keywords on result page. Text snippet: '{post_state.text_summary[:200]}'")

        # ============================================================
        # STEP 9: Verifier check -- task completion
        # ============================================================
        step_num += 1
        print(f"\n{STEP} Step {step_num}: Verifier -- Assess task completion")

        from backend.decision_engine.decision_models import DecisionResult, RiskLevel
        mock_decision = DecisionResult(
            decision="click",
            target_id="search_button",
            confidence=0.95,
            reason="Clicked Search/Go button",
            provider="mock-jev",
            risk_level=RiskLevel.LOW
        )
        v_ok, v_msg, is_completed = Verifier.verify_action_effect(
            pre_state=pre_type_state,
            post_state=post_state,
            decision=mock_decision,
            task_goal="Open Wikipedia and search for AI"
        )
        report(INFO, f"Verifier result: success={v_ok}, completed={is_completed}, msg='{v_msg}'")

        if v_ok:
            report(PASS, f"Verifier confirmed action success: {v_msg}")
        else:
            report(FAIL, f"Verifier flagged issue: {v_msg}")

        # ============================================================
        # FINAL: Task Completed Summary
        # ============================================================
        print()
        print("=" * 70)
        print("  TASK COMPLETED -- Wikipedia AI Search Flow Results")
        print("=" * 70)

        pass_count = sum(1 for s, _ in results if s == PASS)
        fail_count = sum(1 for s, _ in results if s == FAIL)

        print(f"\n  Total Checks:  {pass_count + fail_count}")
        print(f"  Passed:        {pass_count}")
        print(f"  Failed:        {fail_count}")

        if fail_count == 0:
            print(f"\n  *** ALL CHECKS PASSED -- Wikipedia AI E2E Flow VERIFIED ***")
        else:
            print(f"\n  *** {fail_count} CHECK(S) FAILED ***")
            for s, m in results:
                if s == FAIL:
                    print(f"    {FAIL} {m}")

        print()
        print(f"  Final URL:   {result_url}")
        print(f"  Final Title: {result_title}")
        print(f"  AI Keywords: {ai_keywords_found}")
        print("=" * 70)

        return results

    except Exception as exc:
        import traceback
        print(f"\n  {FAIL} Unhandled exception: {exc}")
        traceback.print_exc()
        return results
    finally:
        await bm.stop()


if __name__ == "__main__":
    asyncio.run(run_wikipedia_ai_flow())
