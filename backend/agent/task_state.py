from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from backend.decision_engine.decision_models import DecisionResult

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"

class AgentMetrics(BaseModel):
    steps_count: int = 0
    jev_decisions_count: int = 0
    llm_fallbacks_count: int = 0
    human_approvals_count: int = 0
    successful_actions_count: int = 0
    failed_actions_count: int = 0
    total_decision_latency_ms: float = 0.0
    total_action_latency_ms: float = 0.0
    confidences: List[float] = Field(default_factory=list)

    @property
    def avg_confidence(self) -> float:
        if not self.confidences:
            return 0.0
        return round(sum(self.confidences) / len(self.confidences), 4)

    @property
    def avg_decision_latency_ms(self) -> float:
        total_decisions = self.jev_decisions_count + self.llm_fallbacks_count
        if total_decisions == 0:
            return 0.0
        return round(self.total_decision_latency_ms / total_decisions, 1)

    @property
    def avg_action_latency_ms(self) -> float:
        total_actions = self.successful_actions_count + self.failed_actions_count
        if total_actions == 0:
            return 0.0
        return round(self.total_action_latency_ms / total_actions, 1)

    def to_display_dict(self) -> Dict[str, Any]:
        return {
            "steps": self.steps_count,
            "jev_decisions": self.jev_decisions_count,
            "llm_fallbacks": self.llm_fallbacks_count,
            "human_approvals": self.human_approvals_count,
            "successful_actions": self.successful_actions_count,
            "failed_actions": self.failed_actions_count,
            "avg_confidence": self.avg_confidence,
            "avg_decision_latency_ms": self.avg_decision_latency_ms,
            "avg_action_latency_ms": self.avg_action_latency_ms,
        }

class TaskState(BaseModel):
    task_id: str
    prompt: str
    status: TaskStatus = TaskStatus.PENDING
    max_steps: int = 30
    current_step: int = 0
    current_subgoal: Optional[str] = None
    subgoals: List[str] = Field(default_factory=list)
    recent_actions: List[str] = Field(default_factory=list)
    latest_decision: Optional[DecisionResult] = None
    pending_approval: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metrics: AgentMetrics = Field(default_factory=AgentMetrics)
