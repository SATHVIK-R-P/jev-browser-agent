from enum import Enum
from typing import Tuple
from backend.decision_engine.decision_models import RiskLevel

class RoutingVerdict(str, Enum):
    EXECUTE_AUTO = "execute_auto"
    EXECUTE_LOW_RISK = "execute_low_risk"
    REQUIRE_HUMAN_CONFIRMATION = "require_human_confirmation"
    ESCALATE_LLM = "escalate_llm"

class ConfidenceEvaluator:
    """
    Evaluates decisions based on confidence and action risk level.

    Routing Matrix:
    - HIGH risk: Always requires human confirmation, regardless of confidence.
    - confidence >= auto_execute_threshold (0.90):
        -> EXECUTE_AUTO (if not HIGH risk)
    - low_risk_threshold (0.70) <= confidence < auto_execute_threshold (0.90):
        -> If LOW risk: EXECUTE_LOW_RISK
        -> If MEDIUM risk: REQUIRE_HUMAN_CONFIRMATION
    - confidence < low_risk_threshold (0.70):
        -> ESCALATE_LLM (Send decision to fallback LLM)
    """

    def __init__(
        self,
        auto_execute_threshold: float = 0.90,
        low_risk_threshold: float = 0.70
    ):
        self.auto_execute_threshold = max(0.0, min(1.0, auto_execute_threshold))
        self.low_risk_threshold = max(0.0, min(1.0, low_risk_threshold))

    def evaluate(self, confidence: float, risk_level: RiskLevel) -> Tuple[RoutingVerdict, str]:
        # Clamp confidence to [0.0, 1.0]
        norm_conf = max(0.0, min(1.0, float(confidence)))

        # Rule 1: High risk ALWAYS requires human confirmation
        if risk_level == RiskLevel.HIGH:
            return (
                RoutingVerdict.REQUIRE_HUMAN_CONFIRMATION,
                f"Action classified as HIGH risk ({risk_level.value}). Immediate human confirmation required."
            )

        # Rule 2: High confidence (>= 0.90) and not High risk -> auto execute
        if norm_conf >= self.auto_execute_threshold:
            return (
                RoutingVerdict.EXECUTE_AUTO,
                f"Confidence {norm_conf:.3f} >= {self.auto_execute_threshold:.2f} threshold. Approved for automatic execution."
            )

        # Rule 3: Moderate confidence (0.70 <= conf < 0.90)
        if norm_conf >= self.low_risk_threshold:
            if risk_level == RiskLevel.LOW:
                return (
                    RoutingVerdict.EXECUTE_LOW_RISK,
                    f"Confidence {norm_conf:.3f} >= {self.low_risk_threshold:.2f} and risk is LOW. Executing."
                )
            else:
                return (
                    RoutingVerdict.REQUIRE_HUMAN_CONFIRMATION,
                    f"Confidence {norm_conf:.3f} is moderate, but action risk is {risk_level.value}. Requesting human confirmation."
                )

        # Rule 4: Low confidence (< 0.70) -> Escalate to fallback LLM
        return (
            RoutingVerdict.ESCALATE_LLM,
            f"Confidence {norm_conf:.3f} < {self.low_risk_threshold:.2f}. Escalating decision to fallback LLM."
        )

    def evaluate_llm_result(self, confidence: float, risk_level: RiskLevel) -> Tuple[bool, str]:
        """
        Evaluate fallback LLM decision.
        If fallback LLM confidence is uncertain (< low_risk_threshold) or action is risky, ask human.
        """
        norm_conf = max(0.0, min(1.0, float(confidence)))
        if risk_level == RiskLevel.HIGH:
            return False, "Fallback LLM decision involves HIGH risk. Human confirmation required."
        if norm_conf < self.low_risk_threshold:
            return False, f"Fallback LLM is also uncertain (confidence {norm_conf:.3f} < {self.low_risk_threshold:.2f}). Escalating to human."
        if risk_level == RiskLevel.MEDIUM and norm_conf < self.auto_execute_threshold:
            return False, f"Fallback LLM confidence {norm_conf:.3f} on MEDIUM risk action requires human confirmation."
        return True, f"Fallback LLM decision approved (confidence {norm_conf:.3f})."
