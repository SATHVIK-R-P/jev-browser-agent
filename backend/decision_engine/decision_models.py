from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field

class ActionType(str, Enum):
    CLICK = "click"
    TYPE = "type"
    NAVIGATE = "navigate"
    SCROLL = "scroll"
    SELECT = "select"
    SUBMIT = "submit"
    WAIT = "wait"
    FINISH = "finish"
    ASK_HUMAN = "ask_human"

class DecisionMode(str, Enum):
    CHOICE = "choice"      # Select best single action from candidates
    SCORE = "score"        # Score every candidate action
    NOUL = "noul"          # Binary decision (Yes/No or proceed/abort)

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class CandidateAction(BaseModel):
    id: str = Field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:8]}")
    action_type: ActionType
    target_id: Optional[str] = None  # e.g. "element_7"
    target_selector: Optional[str] = None
    target_text: Optional[str] = None
    target_role: Optional[str] = None
    value: Optional[str] = None  # e.g. text to type or URL to navigate to
    description: str = ""
    reason: Optional[str] = None
    score: Optional[float] = None
    risk_level: RiskLevel = RiskLevel.LOW

    def to_display_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action_type": self.action_type.value,
            "target_id": self.target_id,
            "target_text": self.target_text,
            "value": self.value,
            "description": self.description,
            "score": round(self.score, 4) if self.score is not None else None,
            "risk_level": self.risk_level.value,
        }

class DecisionRequest(BaseModel):
    task_id: str
    step_number: int
    task_goal: str
    current_subgoal: Optional[str] = None
    page_url: str
    page_title: str
    candidates: List[CandidateAction]
    mode: DecisionMode = DecisionMode.CHOICE
    context_notes: Optional[str] = None
    recent_actions: List[str] = Field(default_factory=list)

class DecisionResult(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:10]}")
    decision: str  # ActionType string (e.g. "click", "type", "finish")
    target_id: Optional[str] = None  # e.g. "element_17"
    target_selector: Optional[str] = None
    value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    provider: str  # "jev", "mock-jev", "fallback-llm", "human"
    risk_level: RiskLevel = RiskLevel.LOW
    requires_human: bool = False
    raw_scores: Dict[str, float] = Field(default_factory=dict)
    candidate_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_log_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision": self.decision,
            "target_id": self.target_id,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "provider": self.provider,
            "risk_level": self.risk_level.value,
            "requires_human": self.requires_human,
            "created_at": self.created_at,
        }
