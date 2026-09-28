import time
import logging
from typing import Optional, Tuple
from backend.decision_engine.decision_models import (
    DecisionRequest,
    DecisionResult,
    RiskLevel
)
from backend.decision_engine.jev_client import JEVClientInterface, JEVClientError
from backend.decision_engine.confidence import ConfidenceEvaluator, RoutingVerdict
from backend.decision_engine.fallback_llm import BaseLLMFallback

logger = logging.getLogger(__name__)

class DecisionRouter:
    """
    Coordinates decision routing across:
    1. JEV System-One client
    2. Confidence evaluation & thresholding
    3. Fallback LLM escalation
    4. Human confirmation requirement
    """

    def __init__(
        self,
        jev_client: JEVClientInterface,
        fallback_llm: BaseLLMFallback,
        confidence_evaluator: Optional[ConfidenceEvaluator] = None
    ):
        self.jev_client = jev_client
        self.fallback_llm = fallback_llm
        self.evaluator = confidence_evaluator or ConfidenceEvaluator()

    async def route_decision(self, request: DecisionRequest) -> Tuple[DecisionResult, str]:
        """
        Execute full confidence-aware decision routing workflow.
        Returns (DecisionResult, routing_note).
        """
        start_time = time.time()
        jev_error_note = None

        # Step 1: Call JEV client
        try:
            decision = await self.jev_client.decide_choice(request)
        except JEVClientError as exc:
            logger.warning(f"JEV Client failed ({exc}). Escalating to fallback LLM.")
            jev_error_note = f"JEV error: {exc}"
            decision = None
        except Exception as exc:
            logger.error(f"Unexpected error in JEV Client: {exc}.")
            jev_error_note = f"Unexpected JEV error: {exc}"
            decision = None

        # Step 2: Handle JEV success vs failure
        if decision is not None:
            verdict, verdict_reason = self.evaluator.evaluate(decision.confidence, decision.risk_level)

            if verdict in [RoutingVerdict.EXECUTE_AUTO, RoutingVerdict.EXECUTE_LOW_RISK]:
                decision.requires_human = False
                note = f"Route: JEV -> {verdict.value} ({verdict_reason})"
                return decision, note

            elif verdict == RoutingVerdict.REQUIRE_HUMAN_CONFIRMATION:
                decision.requires_human = True
                note = f"Route: JEV -> Human Confirmation ({verdict_reason})"
                return decision, note

            elif verdict == RoutingVerdict.ESCALATE_LLM:
                logger.info(f"JEV confidence low ({decision.confidence}). Escalating to Fallback LLM.")
                # Proceed to LLM escalation below

        # Step 3: Escalate to Fallback LLM
        llm_decision = await self.fallback_llm.decide(request)
        if jev_error_note:
            llm_decision.reason = f"[{jev_error_note}] {llm_decision.reason}"

        # Step 4: Evaluate Fallback LLM confidence
        approved, eval_msg = self.evaluator.evaluate_llm_result(llm_decision.confidence, llm_decision.risk_level)
        if approved:
            llm_decision.requires_human = False
            note = f"Route: Fallback LLM -> Auto Execute ({eval_msg})"
        else:
            llm_decision.requires_human = True
            note = f"Route: Fallback LLM -> Human Confirmation ({eval_msg})"

        return llm_decision, note
