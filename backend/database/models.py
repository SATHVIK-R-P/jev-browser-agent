from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class TaskRecord(BaseModel):
    id: str
    prompt: str
    status: str = "PENDING"
    max_steps: int = 30
    current_step: int = 0
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

class StepRecord(BaseModel):
    id: str
    task_id: str
    step_number: int
    state_summary: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ObservationRecord(BaseModel):
    id: str
    task_id: str
    step_number: int
    url: str
    title: Optional[str] = None
    element_count: int = 0
    screenshot_path: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CandidateActionsRecord(BaseModel):
    id: str
    task_id: str
    step_number: int
    candidate_json: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DecisionRecord(BaseModel):
    id: str
    task_id: str
    step_number: int
    provider: str
    action_type: str
    target_id: Optional[str] = None
    confidence: float
    reason: Optional[str] = None
    latency_ms: Optional[float] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ActionResultRecord(BaseModel):
    id: str
    task_id: str
    step_number: int
    success: bool
    message: Optional[str] = None
    latency_ms: Optional[float] = None
    verification_result: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ApprovalRecord(BaseModel):
    id: str
    task_id: str
    step_number: int
    action_description: str
    risk_level: str
    status: str
    requested_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    decided_at: Optional[str] = None
