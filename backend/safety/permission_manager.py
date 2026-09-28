from typing import Tuple
from backend.decision_engine.decision_models import RiskLevel, DecisionResult

class PermissionManager:
    """
    Enforces the safety permission policy:
    1. HIGH risk actions NEVER execute automatically under any circumstances.
    2. MEDIUM risk actions require human confirmation unless confidence is exceptionally high (>= 0.90) and auto-execute is enabled.
    3. LOW risk actions can execute automatically when confidence >= 0.70.
    """

    def __init__(self, auto_execute_threshold: float = 0.90, low_risk_threshold: float = 0.70):
        self.auto_execute_threshold = auto_execute_threshold
        self.low_risk_threshold = low_risk_threshold

    def is_execution_permitted(self, decision: DecisionResult, human_approved: bool = False) -> Tuple[bool, str]:
        # If user explicitly approved via UI
        if human_approved:
            return True, "Execution approved by human supervisor."

        # Hard guardrail: HIGH risk MUST have human approval
        if decision.risk_level == RiskLevel.HIGH:
            return False, f"CRITICAL: Action '{decision.decision}' involves HIGH RISK. Automatic execution is prohibited."

        # Medium risk check
        if decision.risk_level == RiskLevel.MEDIUM:
            if decision.confidence >= self.auto_execute_threshold:
                return True, f"MEDIUM risk action auto-permitted due to high confidence ({decision.confidence:.3f})."
            return False, f"MEDIUM risk action requires human confirmation (confidence {decision.confidence:.3f} < {self.auto_execute_threshold})."

        # Low risk check
        if decision.risk_level == RiskLevel.LOW:
            if decision.confidence >= self.low_risk_threshold:
                return True, f"LOW risk action permitted (confidence {decision.confidence:.3f} >= {self.low_risk_threshold})."
            return False, f"LOW risk action requires confirmation due to low confidence ({decision.confidence:.3f})."

        return False, "Action execution blocked by default safety policy."
