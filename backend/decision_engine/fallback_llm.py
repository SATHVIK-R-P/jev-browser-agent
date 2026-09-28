import abc
import json
import logging
from typing import Optional, Dict, Any
import httpx
from backend.decision_engine.decision_models import (
    DecisionRequest,
    DecisionResult,
    RiskLevel,
    ActionType
)

logger = logging.getLogger(__name__)

class LLMFallbackError(Exception):
    """Exception for LLM fallback errors."""
    pass

class BaseLLMFallback(abc.ABC):
    """Abstract interface for fallback LLM decision providers."""

    @abc.abstractmethod
    async def decide(self, request: DecisionRequest) -> DecisionResult:
        """Analyze page state and candidates, returning structured decision."""
        pass


class MockLLMFallback(BaseLLMFallback):
    """
    Mock LLM provider for local testing and deterministic fallback behavior.
    """

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        if not request.candidates:
            return DecisionResult(
                decision=ActionType.WAIT.value,
                confidence=0.60,
                reason="Fallback LLM: No available actions detected on page.",
                provider="fallback-llm-mock",
                risk_level=RiskLevel.LOW
            )

        # Analyze candidates with high-level heuristics
        best_cand = None
        best_score = -1.0

        for cand in request.candidates:
            score = 0.50
            text_corpus = f"{cand.description} {cand.target_text or ''} {cand.value or ''}".lower()
            goal_lower = request.task_goal.lower()

            if any(term in text_corpus for term in goal_lower.split()):
                score += 0.30

            if cand.action_type in [ActionType.TYPE, ActionType.CLICK]:
                score += 0.15

            if score > best_score:
                best_score = score
                best_cand = cand

        best_cand = best_cand or request.candidates[0]
        confidence = min(0.88, max(0.65, best_score))

        return DecisionResult(
            decision=best_cand.action_type.value,
            target_id=best_cand.target_id,
            target_selector=best_cand.target_selector,
            value=best_cand.value,
            confidence=round(confidence, 4),
            reason=f"Fallback LLM reasoned that '{best_cand.description}' directly advances subgoal.",
            provider="fallback-llm-mock",
            risk_level=best_cand.risk_level,
            candidate_id=best_cand.id
        )


class OpenAICompatibleLLM(BaseLLMFallback):
    """
    OpenAI-compatible Fallback LLM client (works with OpenAI, vLLM, Ollama, Groq, etc.).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: float = 15.0
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        if not self.api_key:
            logger.warning("OpenAI API key missing, falling back to Mock LLM.")
            return await MockLLMFallback().decide(request)

        endpoint = f"{self.base_url}/chat/completions"
        system_prompt = (
            "You are an autonomous web browser agent decision system. "
            "Given the user task goal, current page state, and candidate actions, "
            "select the best candidate action or propose an action. "
            "Output JSON with keys: decision, target_id, value, confidence (0.0-1.0), reason."
        )

        user_content = {
            "task_goal": request.task_goal,
            "page_url": request.page_url,
            "page_title": request.page_title,
            "candidates": [c.to_display_dict() for c in request.candidates]
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_content, indent=2)}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code != 200:
                raise LLMFallbackError(f"LLM API returned HTTP {resp.status_code}: {resp.text}")

            res_json = resp.json()
            content = res_json["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            target_id = parsed.get("target_id")
            matching_cand = next((c for c in request.candidates if c.target_id == target_id), None)
            risk = matching_cand.risk_level if matching_cand else RiskLevel.LOW

            return DecisionResult(
                decision=parsed.get("decision", "wait"),
                target_id=target_id,
                target_selector=matching_cand.target_selector if matching_cand else None,
                value=parsed.get("value") or (matching_cand.value if matching_cand else None),
                confidence=float(parsed.get("confidence", 0.75)),
                reason=parsed.get("reason", "Decision derived from fallback LLM."),
                provider="fallback-llm-openai",
                risk_level=risk,
                candidate_id=matching_cand.id if matching_cand else None
            )
        except Exception as exc:
            logger.error(f"Fallback LLM error: {exc}. Using mock fallback.")
            return await MockLLMFallback().decide(request)


class GeminiLLMFallback(BaseLLMFallback):
    """
    Google Gemini API fallback provider via official REST endpoint.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        timeout: float = 15.0
    ):
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        if not self.api_key:
            return await MockLLMFallback().decide(request)

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        prompt = (
            f"You are a browser agent decision engine.\n"
            f"Task: {request.task_goal}\n"
            f"URL: {request.page_url} ({request.page_title})\n"
            f"Candidates: {json.dumps([c.to_display_dict() for c in request.candidates])}\n"
            f"Select the best candidate action and reply in valid JSON format: "
            f'{{"decision": "click|type|navigate|finish", "target_id": "element_id", "confidence": 0.85, "reason": "why"}}'
        )

        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
            if res.status_code != 200:
                raise LLMFallbackError(f"Gemini API returned HTTP {res.status_code}: {res.text}")

            data = res.json()
            text_resp = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text_resp)

            target_id = parsed.get("target_id")
            matching_cand = next((c for c in request.candidates if c.target_id == target_id), None)
            risk = matching_cand.risk_level if matching_cand else RiskLevel.LOW

            return DecisionResult(
                decision=parsed.get("decision", "wait"),
                target_id=target_id,
                target_selector=matching_cand.target_selector if matching_cand else None,
                value=parsed.get("value") or (matching_cand.value if matching_cand else None),
                confidence=float(parsed.get("confidence", 0.78)),
                reason=parsed.get("reason", "Decision derived from Gemini LLM."),
                provider="fallback-llm-gemini",
                risk_level=risk,
                candidate_id=matching_cand.id if matching_cand else None
            )
        except Exception as exc:
            logger.error(f"Gemini LLM fallback error: {exc}. Defaulting to mock fallback.")
            return await MockLLMFallback().decide(request)


def create_fallback_llm(
    provider: str = "mock",
    api_key: str = "",
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    timeout_seconds: float = 15.0
) -> BaseLLMFallback:
    """Factory creating configured Fallback LLM instance."""
    p = provider.lower()
    if p in ["openai", "openai-compatible"]:
        return OpenAICompatibleLLM(api_key=api_key, base_url=base_url, model=model, timeout=timeout_seconds)
    elif p == "gemini":
        return GeminiLLMFallback(api_key=api_key, model=model, timeout=timeout_seconds)
    return MockLLMFallback()
