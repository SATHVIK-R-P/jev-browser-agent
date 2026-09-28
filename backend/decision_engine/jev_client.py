import abc
import time
import re
from typing import List, Dict, Any, Optional
import httpx
from backend.decision_engine.decision_models import (
    CandidateAction,
    DecisionRequest,
    DecisionResult,
    DecisionMode,
    RiskLevel,
    ActionType
)

class JEVClientError(Exception):
    """Base exception for JEV Client errors."""
    pass

class JEVAuthenticationError(JEVClientError):
    """Raised when JEV API key is missing or invalid."""
    pass

class JEVNetworkError(JEVClientError):
    """Raised when JEV API connection or timeout fails."""
    pass

class JEVClientInterface(abc.ABC):
    """Abstract interface for JEV System-One Decision Client."""

    @abc.abstractmethod
    async def decide_choice(self, request: DecisionRequest) -> DecisionResult:
        """CHOICE mode: choose the single best action from candidate actions."""
        pass

    @abc.abstractmethod
    async def score_candidates(self, request: DecisionRequest) -> List[CandidateAction]:
        """SCORE mode: score every candidate action."""
        pass

    @abc.abstractmethod
    async def decide_noul(self, question: str, context: Optional[str] = None) -> Dict[str, Any]:
        """NOUL mode: binary Yes/No decision."""
        pass


class MockJEVClient(JEVClientInterface):
    """
    Mock JEV System-One Decision Client.
    Deterministic, heuristic-grounded decision making for testing, CI/CD,
    and running immediately without an API key in GitHub Codespaces.
    """

    def __init__(self, latency_simulate: float = 0.05):
        self.latency_simulate = latency_simulate

    def _calculate_candidate_score(self, candidate: CandidateAction, goal: str, subgoal: Optional[str]) -> float:
        """
        Evaluate semantic match of a candidate action against user goal and current subgoal.
        """
        combined_goal = f"{goal} {subgoal or ''}".lower()
        cand_text = f"{candidate.description} {candidate.target_text or ''} {candidate.value or ''} {candidate.target_role or ''} {candidate.target_id or ''}".lower()

        base_score = 0.40

        # Goal term matching
        keywords = re.findall(r"\b\w{3,}\b", combined_goal)
        matches = [kw for kw in keywords if kw in cand_text]
        if keywords:
            base_score += 0.45 * (len(matches) / len(keywords))

        # Action-type specific relevance
        if "search" in combined_goal or "find" in combined_goal:
            if candidate.action_type == ActionType.TYPE and any(k in cand_text for k in ["search", "input", "query", "find"]):
                base_score += 0.35
            elif candidate.action_type == ActionType.CLICK and any(k in cand_text for k in ["search", "submit", "go", "btn"]):
                base_score += 0.30

        if "filter" in combined_goal or "under" in combined_goal or "cheap" in combined_goal:
            if candidate.action_type == ActionType.CLICK and any(k in cand_text for k in ["filter", "price", "low to high", "sort", "cheapest", "under"]):
                base_score += 0.40

        if "open" in combined_goal or "article" in combined_goal or "link" in combined_goal:
            if candidate.action_type == ActionType.CLICK and candidate.target_role in ["link", "heading", "button"]:
                base_score += 0.25

        if candidate.action_type == ActionType.FINISH:
            if any(term in cand_text for term in ["goal satisfied", "completed", "found", "finished"]):
                base_score += 0.35

        # Cap between 0.10 and 0.985
        return max(0.12, min(0.985, base_score))

    async def score_candidates(self, request: DecisionRequest) -> List[CandidateAction]:
        scored_candidates = []
        for cand in request.candidates:
            score = self._calculate_candidate_score(cand, request.task_goal, request.current_subgoal)
            updated = cand.model_copy()
            updated.score = round(score, 4)
            scored_candidates.append(updated)

        # Sort descending by score
        scored_candidates.sort(key=lambda c: (c.score or 0.0), reverse=True)
        return scored_candidates

    async def decide_choice(self, request: DecisionRequest) -> DecisionResult:
        if self.latency_simulate > 0:
            time.sleep(self.latency_simulate)

        if not request.candidates:
            return DecisionResult(
                decision=ActionType.WAIT.value,
                confidence=0.50,
                reason="No candidate actions available on current page.",
                provider="mock-jev",
                risk_level=RiskLevel.LOW
            )

        scored = await self.score_candidates(request)
        best = scored[0]

        # Calculate softmax-like confidence or difference margin
        top_score = best.score or 0.85
        raw_scores = {c.id: (c.score or 0.0) for c in scored}

        # If best score is convincingly high, assign high confidence (e.g. 0.92 - 0.97)
        if top_score >= 0.70:
            confidence = min(0.975, top_score + 0.02)
        else:
            confidence = max(0.45, top_score - 0.05)

        reason = best.reason or f"Selected optimal action '{best.action_type.value}' targeting {best.target_id or 'viewport'} (Match Score: {top_score:.3f})"

        return DecisionResult(
            decision=best.action_type.value,
            target_id=best.target_id,
            target_selector=best.target_selector,
            value=best.value,
            confidence=round(confidence, 4),
            reason=reason,
            provider="mock-jev",
            risk_level=best.risk_level,
            candidate_id=best.id,
            raw_scores=raw_scores
        )

    async def decide_noul(self, question: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Binary Yes/No bounded decision."""
        q_lower = question.lower()
        if any(term in q_lower for term in ["safe", "proceed", "relevant", "continue", "found"]):
            decision = True
            confidence = 0.94
        else:
            decision = False
            confidence = 0.88

        return {
            "decision": "YES" if decision else "NO",
            "boolean": decision,
            "confidence": confidence,
            "provider": "mock-jev"
        }


class RealJEVClient(JEVClientInterface):
    """
    Client for live JEV / System-One API.
    Handles authentication, payloads, structured schemas, timeouts, and error classification.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.jev.ai/v1",
        model: str = "system-one-v1",
        timeout_seconds: float = 10.0
    ):
        self.api_key = api_key.strip()
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise JEVAuthenticationError("JEV_API_KEY is not configured.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "JEV-Browser-Agent/1.0",
        }

    async def decide_choice(self, request: DecisionRequest) -> DecisionResult:
        if not self.api_key:
            raise JEVAuthenticationError("JEV API key is missing. Set JEV_API_KEY or use JEV_MODE=mock.")

        endpoint = f"{self.api_url}/decisions/choice"
        payload = {
            "model": self.model,
            "task_id": request.task_id,
            "step": request.step_number,
            "goal": request.task_goal,
            "subgoal": request.current_subgoal,
            "page": {
                "url": request.page_url,
                "title": request.page_title,
            },
            "candidates": [
                {
                    "id": c.id,
                    "action": c.action_type.value,
                    "target_id": c.target_id,
                    "target_text": c.target_text,
                    "target_role": c.target_role,
                    "value": c.value,
                    "description": c.description,
                    "risk_level": c.risk_level.value,
                }
                for c in request.candidates
            ],
            "context": request.context_notes,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload, headers=self._headers())

            if response.status_code == 401:
                raise JEVAuthenticationError("JEV API authorization failed (401). Check JEV_API_KEY.")
            elif response.status_code == 429:
                raise JEVClientError("JEV API rate limit exceeded (429).")
            elif response.status_code != 200:
                raise JEVClientError(f"JEV API returned unexpected HTTP {response.status_code}: {response.text}")

            data = response.json()
            # Normalize JEV response schema
            decision_val = data.get("decision") or data.get("selected_action") or "wait"
            target_id = data.get("target_id")
            confidence = float(data.get("confidence", 0.85))
            reason = data.get("reason", "Decision by JEV System-One.")
            raw_scores = data.get("scores", {})

            # Match candidate to extract selector and risk
            matching_cand = next((c for c in request.candidates if c.target_id == target_id or c.id == data.get("candidate_id")), None)
            risk_level = matching_cand.risk_level if matching_cand else RiskLevel.LOW
            selector = matching_cand.target_selector if matching_cand else None

            return DecisionResult(
                decision=decision_val,
                target_id=target_id,
                target_selector=selector,
                value=matching_cand.value if matching_cand else None,
                confidence=round(confidence, 4),
                reason=reason,
                provider="jev",
                risk_level=risk_level,
                candidate_id=matching_cand.id if matching_cand else None,
                raw_scores=raw_scores
            )

        except httpx.RequestError as exc:
            raise JEVNetworkError(f"Network error communicating with JEV API at {endpoint}: {exc}") from exc
        except (ValueError, KeyError) as exc:
            raise JEVClientError(f"Malformed JSON response from JEV API: {exc}") from exc

    async def score_candidates(self, request: DecisionRequest) -> List[CandidateAction]:
        if not self.api_key:
            raise JEVAuthenticationError("JEV API key is missing.")

        endpoint = f"{self.api_url}/decisions/score"
        payload = {
            "model": self.model,
            "goal": request.task_goal,
            "candidates": [c.model_dump() for c in request.candidates]
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(endpoint, json=payload, headers=self._headers())
            if res.status_code != 200:
                raise JEVClientError(f"JEV scoring failed: {res.status_code}")
            data = res.json()
            score_map = data.get("scores", {})
            updated = []
            for c in request.candidates:
                copy_c = c.model_copy()
                copy_c.score = float(score_map.get(c.id, 0.5))
                updated.append(copy_c)
            updated.sort(key=lambda x: (x.score or 0.0), reverse=True)
            return updated
        except Exception as exc:
            raise JEVClientError(f"JEV score failed: {exc}") from exc

    async def decide_noul(self, question: str, context: Optional[str] = None) -> Dict[str, Any]:
        if not self.api_key:
            raise JEVAuthenticationError("JEV API key is missing.")
        endpoint = f"{self.api_url}/decisions/noul"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(endpoint, json={"question": question, "context": context}, headers=self._headers())
            data = res.json()
            return {
                "decision": data.get("decision", "NO"),
                "boolean": bool(data.get("boolean", False)),
                "confidence": float(data.get("confidence", 0.5)),
                "provider": "jev"
            }
        except Exception as exc:
            raise JEVClientError(f"JEV noul failed: {exc}") from exc


def create_jev_client(
    mode: str = "mock",
    api_key: str = "",
    api_url: str = "https://api.jev.ai/v1",
    model: str = "system-one-v1",
    timeout_seconds: float = 10.0
) -> JEVClientInterface:
    """Factory creating appropriate JEV client adapter."""
    if mode.lower() == "real":
        return RealJEVClient(
            api_key=api_key,
            api_url=api_url,
            model=model,
            timeout_seconds=timeout_seconds
        )
    return MockJEVClient()
