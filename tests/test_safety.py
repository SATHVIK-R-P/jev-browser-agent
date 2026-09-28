import pytest
import asyncio
from backend.decision_engine.decision_models import ActionType, RiskLevel, DecisionResult
from backend.safety.risk_classifier import RiskClassifier
from backend.safety.permission_manager import PermissionManager
from backend.safety.confirmation_manager import ConfirmationManager, ConfirmationStatus

def test_risk_classifier_levels():
    # LOW risk tests
    risk, reason = RiskClassifier.classify(ActionType.CLICK, target_text="Read Article", description="Navigate to article")
    assert risk == RiskLevel.LOW

    risk, reason = RiskClassifier.classify(ActionType.SCROLL, description="Scroll down")
    assert risk == RiskLevel.LOW

    # MEDIUM risk tests
    risk, reason = RiskClassifier.classify(ActionType.SUBMIT, description="Submit inquiry form")
    assert risk == RiskLevel.MEDIUM

    risk, reason = RiskClassifier.classify(ActionType.CLICK, target_text="Upload Resume", description="Upload file")
    assert risk == RiskLevel.MEDIUM

    # HIGH risk tests
    risk, reason = RiskClassifier.classify(ActionType.CLICK, target_text="Buy Now", description="Purchase item")
    assert risk == RiskLevel.HIGH

    risk, reason = RiskClassifier.classify(ActionType.TYPE, target_text="Password", value="supersecret", description="Enter password")
    assert risk == RiskLevel.HIGH

    risk, reason = RiskClassifier.classify(ActionType.CLICK, target_text="Delete Account", description="Remove data")
    assert risk == RiskLevel.HIGH

def test_credential_sanitization():
    raw = "User entered password: Secret123! with card 4111 2222 3333 4444 and api_key=xyz987"
    sanitized = RiskClassifier.sanitize(raw)
    assert "Secret123!" not in sanitized
    assert "4111 2222 3333 4444" not in sanitized
    assert "xyz987" not in sanitized

def test_permission_manager():
    pm = PermissionManager(auto_execute_threshold=0.90, low_risk_threshold=0.70)

    # HIGH risk should NEVER auto execute regardless of high confidence
    high_decision = DecisionResult(
        decision="click",
        confidence=0.99,
        reason="Purchase order",
        provider="mock-jev",
        risk_level=RiskLevel.HIGH
    )
    permitted, msg = pm.is_execution_permitted(high_decision, human_approved=False)
    assert permitted is False
    assert "HIGH RISK" in msg

    # With human approval, it becomes permitted
    permitted, msg = pm.is_execution_permitted(high_decision, human_approved=True)
    assert permitted is True

    # LOW risk with high confidence -> permitted
    low_high_conf = DecisionResult(
        decision="click",
        confidence=0.95,
        reason="Click article link",
        provider="mock-jev",
        risk_level=RiskLevel.LOW
    )
    permitted, _ = pm.is_execution_permitted(low_high_conf)
    assert permitted is True

    # LOW risk with low confidence (< 0.70) -> requires confirmation
    low_low_conf = DecisionResult(
        decision="click",
        confidence=0.55,
        reason="Uncertain link",
        provider="mock-jev",
        risk_level=RiskLevel.LOW
    )
    permitted, _ = pm.is_execution_permitted(low_low_conf)
    assert permitted is False

    # MEDIUM risk with moderate confidence -> requires confirmation
    med_mod_conf = DecisionResult(
        decision="submit",
        confidence=0.82,
        reason="Submit newsletter",
        provider="mock-jev",
        risk_level=RiskLevel.MEDIUM
    )
    permitted, _ = pm.is_execution_permitted(med_mod_conf)
    assert permitted is False

@pytest.mark.asyncio
async def test_confirmation_manager_lifecycle():
    cm = ConfirmationManager()
    req = cm.create_request(
        task_id="task_test_1",
        step_number=1,
        action_description="Click 'Confirm Payment'",
        risk_level=RiskLevel.HIGH,
        reason="High financial risk"
    )

    assert req.status == ConfirmationStatus.PENDING

    # Asynchronously resolve approval in background
    async def resolve_later():
        await asyncio.sleep(0.05)
        cm.resolve(req.id, approved=True)

    asyncio.create_task(resolve_later())

    approved = await cm.wait_for_decision(req.id, timeout_seconds=2.0)
    assert approved is True
    assert req.status == ConfirmationStatus.APPROVED
