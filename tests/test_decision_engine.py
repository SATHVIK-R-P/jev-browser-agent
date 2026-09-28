import pytest
from backend.decision_engine.decision_models import (
    CandidateAction,
    DecisionRequest,
    DecisionResult,
    DecisionMode,
    RiskLevel,
    ActionType
)
from backend.decision_engine.confidence import ConfidenceEvaluator, RoutingVerdict
from backend.decision_engine.jev_client import MockJEVClient, RealJEVClient, JEVAuthenticationError
from backend.decision_engine.fallback_llm import MockLLMFallback
from backend.decision_engine.decision_router import DecisionRouter

def test_confidence_evaluator_thresholds():
    evaluator = ConfidenceEvaluator(auto_execute_threshold=0.90, low_risk_threshold=0.70)

    # 1. High confidence (>= 0.90), LOW risk -> EXECUTE_AUTO
    verdict, _ = evaluator.evaluate(confidence=0.95, risk_level=RiskLevel.LOW)
    assert verdict == RoutingVerdict.EXECUTE_AUTO

    # 2. Moderate confidence (0.75), LOW risk -> EXECUTE_LOW_RISK
    verdict, _ = evaluator.evaluate(confidence=0.75, risk_level=RiskLevel.LOW)
    assert verdict == RoutingVerdict.EXECUTE_LOW_RISK

    # 3. Moderate confidence (0.80), MEDIUM risk -> REQUIRE_HUMAN_CONFIRMATION
    verdict, _ = evaluator.evaluate(confidence=0.80, risk_level=RiskLevel.MEDIUM)
    assert verdict == RoutingVerdict.REQUIRE_HUMAN_CONFIRMATION

    # 4. HIGH risk -> Always REQUIRE_HUMAN_CONFIRMATION
    verdict, _ = evaluator.evaluate(confidence=0.99, risk_level=RiskLevel.HIGH)
    assert verdict == RoutingVerdict.REQUIRE_HUMAN_CONFIRMATION

    # 5. Low confidence (< 0.70) -> ESCALATE_LLM
    verdict, _ = evaluator.evaluate(confidence=0.62, risk_level=RiskLevel.LOW)
    assert verdict == RoutingVerdict.ESCALATE_LLM

@pytest.mark.asyncio
async def test_mock_jev_client_choice_and_score():
    client = MockJEVClient(latency_simulate=0.0)

    candidates = [
        CandidateAction(
            id="c1",
            action_type=ActionType.CLICK,
            target_id="element_1",
            target_text="About Us",
            description="Click About Us",
            risk_level=RiskLevel.LOW
        ),
        CandidateAction(
            id="c2",
            action_type=ActionType.TYPE,
            target_id="element_2",
            target_text="Search",
            value="artificial intelligence",
            description="Type 'artificial intelligence' into search input",
            risk_level=RiskLevel.LOW
        ),
        CandidateAction(
            id="c3",
            action_type=ActionType.CLICK,
            target_id="element_3",
            target_text="Privacy Policy",
            description="Click privacy policy",
            risk_level=RiskLevel.LOW
        ),
    ]

    req = DecisionRequest(
        task_id="test_task_1",
        step_number=1,
        task_goal="Search for artificial intelligence",
        current_subgoal="Type query into search input",
        page_url="https://www.wikipedia.org",
        page_title="Wikipedia",
        candidates=candidates
    )

    # Test scoring
    scored = await client.score_candidates(req)
    assert len(scored) == 3
    # c2 matches goal and action best
    assert scored[0].id == "c2"
    assert scored[0].score > scored[1].score

    # Test choice
    decision = await client.decide_choice(req)
    assert isinstance(decision, DecisionResult)
    assert decision.decision == ActionType.TYPE.value
    assert decision.target_id == "element_2"
    assert decision.provider == "mock-jev"
    assert decision.confidence >= 0.90

@pytest.mark.asyncio
async def test_mock_jev_noul():
    client = MockJEVClient(latency_simulate=0.0)
    res = await client.decide_noul("Is it safe to proceed?")
    assert res["boolean"] is True
    assert res["decision"] == "YES"
    assert res["confidence"] > 0.8

@pytest.mark.asyncio
async def test_real_jev_missing_key_error():
    client = RealJEVClient(api_key="")
    req = DecisionRequest(
        task_id="t1",
        step_number=1,
        task_goal="test",
        page_url="http://test.com",
        page_title="Test",
        candidates=[]
    )
    with pytest.raises(JEVAuthenticationError):
        await client.decide_choice(req)

@pytest.mark.asyncio
async def test_decision_router_flow():
    jev_client = MockJEVClient(latency_simulate=0.0)
    llm = MockLLMFallback()
    router = DecisionRouter(jev_client=jev_client, fallback_llm=llm)

    # High-confidence scenario
    req_high = DecisionRequest(
        task_id="t_route_1",
        step_number=1,
        task_goal="Search for Python Playwright",
        current_subgoal="Enter search query",
        page_url="https://duckduckgo.com",
        page_title="DuckDuckGo",
        candidates=[
            CandidateAction(
                id="c_search",
                action_type=ActionType.TYPE,
                target_id="element_1",
                value="Python Playwright",
                description="Type Python Playwright into search box",
                risk_level=RiskLevel.LOW
            )
        ]
    )

    decision, note = await router.route_decision(req_high)
    assert decision.decision == ActionType.TYPE.value
    assert decision.requires_human is False
    assert "JEV" in note
