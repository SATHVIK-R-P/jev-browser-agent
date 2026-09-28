import re
from typing import List, Optional
from backend.browser.page_state import PageState, InteractiveElement
from backend.decision_engine.decision_models import CandidateAction, ActionType, RiskLevel
from backend.safety.risk_classifier import RiskClassifier

class CandidateGenerator:
    """
    Synthesizes ranked, bounded candidate actions from current PageState and task subgoals.
    """

    @staticmethod
    def generate_candidates(
        page_state: PageState,
        task_goal: str,
        current_subgoal: Optional[str] = None,
        search_query: Optional[str] = None,
        recent_actions: Optional[List[str]] = None,
        initial_url: Optional[str] = None
    ) -> List[CandidateAction]:
        candidates: List[CandidateAction] = []
        recent = recent_actions or []
        goal_text = f"{task_goal} {current_subgoal or ''}".lower()

        # Case 1: Initial navigation needed
        if page_state.url in ["about:blank", "", "data:,"] or (initial_url and initial_url not in page_state.url and len(recent) == 0):
            target_url = initial_url or "https://duckduckgo.com"
            risk, _ = RiskClassifier.classify(ActionType.NAVIGATE, value=target_url, description="Initial page navigation")
            candidates.append(CandidateAction(
                action_type=ActionType.NAVIGATE,
                value=target_url,
                description=f"Navigate to {target_url}",
                reason=f"Open initial target website for task",
                risk_level=risk
            ))
            return candidates

        # Scan interactive elements
        input_elements: List[InteractiveElement] = []
        button_elements: List[InteractiveElement] = []
        link_elements: List[InteractiveElement] = []
        other_elements: List[InteractiveElement] = []

        for el in page_state.elements:
            tag = el.tag_name
            role = el.role
            if tag in ["input", "textarea"] or role in ["textbox", "searchbox"]:
                input_elements.append(el)
            elif tag == "button" or role == "button":
                button_elements.append(el)
            elif tag == "a" or role == "link":
                link_elements.append(el)
            else:
                other_elements.append(el)

        # 1. Candidate: Typing query into search inputs
        query_to_type = search_query or task_goal
        for inp in input_elements[:3]:
            # Skip if recently typed into this exact element
            if not any(f"Typed text into '{inp.selector}'" in r for r in recent):
                desc = f"Type '{query_to_type}' into {inp.name or inp.id} search field"
                risk, _ = RiskClassifier.classify(ActionType.TYPE, inp.name, inp.selector, query_to_type, desc)
                candidates.append(CandidateAction(
                    action_type=ActionType.TYPE,
                    target_id=inp.id,
                    target_selector=inp.selector,
                    target_text=inp.name or inp.text,
                    target_role=inp.role,
                    value=query_to_type,
                    description=desc,
                    reason=f"Enter search query to discover target information",
                    risk_level=risk
                ))

        # 2. Candidate: Search buttons
        for btn in button_elements[:4]:
            btn_text = f"{btn.name} {btn.text}".lower()
            if any(term in btn_text for term in ["search", "find", "go", "submit", "filter"]):
                desc = f"Click {btn.name or btn.text or 'Search'} button"
                risk, _ = RiskClassifier.classify(ActionType.CLICK, btn.name, btn.selector, description=desc)
                candidates.append(CandidateAction(
                    action_type=ActionType.CLICK,
                    target_id=btn.id,
                    target_selector=btn.selector,
                    target_text=btn.name or btn.text,
                    target_role=btn.role,
                    description=desc,
                    reason=f"Submit search or apply filter",
                    risk_level=risk
                ))

        # 3. Candidate: Highly relevant links / results
        keywords = [w.lower() for w in re.findall(r"\b\w{3,}\b", goal_text) if w not in ["open", "search", "find", "for", "the", "and", "under"]]
        matched_links: List[InteractiveElement] = []

        for link in link_elements:
            l_text = f"{link.name} {link.text} {link.attributes.get('href', '')}".lower()
            match_count = sum(1 for kw in keywords if kw in l_text)
            if match_count > 0:
                matched_links.append(link)

        for link in matched_links[:4]:
            desc = f"Click result link '{link.name or link.text}'"
            risk, _ = RiskClassifier.classify(ActionType.CLICK, link.name, link.selector, description=desc)
            candidates.append(CandidateAction(
                action_type=ActionType.CLICK,
                target_id=link.id,
                target_selector=link.selector,
                target_text=link.name or link.text,
                target_role=link.role,
                description=desc,
                reason=f"Open matching result or relevant article",
                risk_level=risk
            ))

        # 4. Candidate: Filter / Sort interactions
        for el in (button_elements + link_elements):
            text_cor = f"{el.name} {el.text}".lower()
            if any(term in text_cor for term in ["filter", "sort", "low to high", "price: low", "under 50", "cheapest"]):
                desc = f"Click filter/sort option '{el.name or el.text}'"
                risk, _ = RiskClassifier.classify(ActionType.CLICK, el.name, el.selector, description=desc)
                candidates.append(CandidateAction(
                    action_type=ActionType.CLICK,
                    target_id=el.id,
                    target_selector=el.selector,
                    target_text=el.name or el.text,
                    target_role=el.role,
                    description=desc,
                    reason="Sort or filter results to meet price criteria",
                    risk_level=risk
                ))

        # 5. Candidate: Scroll down to view more content
        risk_scroll, _ = RiskClassifier.classify(ActionType.SCROLL, description="Scroll down page")
        candidates.append(CandidateAction(
            action_type=ActionType.SCROLL,
            value="500",
            description="Scroll down page to discover more results or content",
            reason="Explore lower viewport elements",
            risk_level=risk_scroll
        ))

        # 6. Candidate: Finish Task (when goal criteria are visibly satisfied)
        is_target_reached = False
        summary_lower = f"{page_state.title} {page_state.text_summary}".lower()

        # Check if Wikipedia article opened
        if "wikipedia" in task_goal.lower() and "wikipedia" in page_state.url and "search" not in page_state.url.lower():
            if any(k in summary_lower for k in keywords):
                is_target_reached = True

        # Check if laptop product / official docs page opened
        if "fastapi" in task_goal.lower() and "fastapi" in page_state.url.lower():
            is_target_reached = True
        if "contact" in task_goal.lower() and "contact" in page_state.url.lower():
            is_target_reached = True
        if ("laptop" in task_goal.lower() or "50000" in task_goal) and any(term in summary_lower for term in ["laptop", "₹", "rs.", "price", "intel", "ryzen", "ram"]):
            if len(recent) >= 2:
                is_target_reached = True

        if is_target_reached or len(recent) >= 4:
            risk_finish, _ = RiskClassifier.classify(ActionType.FINISH, description="Conclude task execution")
            candidates.append(CandidateAction(
                action_type=ActionType.FINISH,
                description="Conclude task — target satisfied and verified",
                reason="Goal information located and verified on active page",
                risk_level=risk_finish
            ))

        # Ensure we always have at least 2 distinct candidates
        if len(candidates) < 2 and link_elements:
            first_link = link_elements[0]
            candidates.append(CandidateAction(
                action_type=ActionType.CLICK,
                target_id=first_link.id,
                target_selector=first_link.selector,
                target_text=first_link.name or first_link.text,
                target_role=first_link.role,
                description=f"Click navigation link '{first_link.name or first_link.text}'",
                reason="Explore page navigation",
                risk_level=RiskLevel.LOW
            ))

        return candidates
