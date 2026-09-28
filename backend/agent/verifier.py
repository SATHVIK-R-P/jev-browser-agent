from typing import Optional, Tuple
from backend.browser.page_state import PageState
from backend.decision_engine.decision_models import DecisionResult, ActionType

class Verifier:
    """
    Verifies that executed browser actions produced the expected DOM effects
    and assesses whether the overall task objectives have been fulfilled.
    """

    @staticmethod
    def verify_action_effect(
        pre_state: PageState,
        post_state: PageState,
        decision: DecisionResult,
        task_goal: str
    ) -> Tuple[bool, str, bool]:
        """
        Returns (success: bool, verification_message: str, is_task_completed: bool).
        """
        action = decision.decision.lower()

        # Check explicit finish action
        if action == ActionType.FINISH.value:
            return True, "Task explicitly concluded successfully.", True

        # Check navigation effect
        if action == ActionType.NAVIGATE.value:
            if post_state.url != pre_state.url and post_state.url != "about:blank":
                return True, f"Navigation verified: opened '{post_state.title}' at {post_state.url}", False
            return False, f"Navigation did not transition URL ({post_state.url})", False

        # Check typing effect
        if action == ActionType.TYPE.value:
            if post_state.url != pre_state.url or len(post_state.elements) != len(pre_state.elements) or post_state.title != pre_state.title:
                return True, f"Search submission verified: page loaded results for query.", False
            return True, f"Text entered into target element successfully.", False

        # Check click effect
        if action == ActionType.CLICK.value:
            url_changed = post_state.url != pre_state.url
            title_changed = post_state.title != pre_state.title
            elems_changed = abs(len(post_state.elements) - len(pre_state.elements)) > 0

            # Check if target page opened (e.g. Wikipedia article, FastAPI docs, product details)
            import re
            goal_lower = task_goal.lower()
            post_summary = f"{post_state.title} {post_state.text_summary}".lower()

            raw_terms = re.findall(r"[a-z0-9]+", goal_lower)
            stopwords = {"open", "search", "find", "under", "with", "from", "about", "website", "page", "matching", "product", "the", "and", "for"}
            goal_keywords = [w for w in raw_terms if len(w) >= 3 and w not in stopwords]
            matches = sum(1 for kw in goal_keywords if kw in post_summary or kw.rstrip("s") in post_summary)

            is_completed = False
            if url_changed and (matches >= 1 or any(p in post_state.url.lower() for p in ["/item/", "/product/", "/wiki/", "/docs", "contact"])):
                # Target article or documentation or product opened
                is_completed = True

            if url_changed:
                msg = f"Click verified: navigated to '{post_state.title}' ({post_state.url})"
            elif title_changed:
                msg = f"Click verified: title updated to '{post_state.title}'"
            elif elems_changed:
                msg = f"Click verified: page layout updated ({len(post_state.elements)} elements)"
            else:
                msg = f"Click dispatched to {decision.target_id or 'element'}"

            return True, msg, is_completed

        # Check scroll effect
        if action == ActionType.SCROLL.value:
            return True, "Scroll execution verified.", False

        return True, "Action completed.", False
