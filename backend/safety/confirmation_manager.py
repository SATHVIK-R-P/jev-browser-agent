import asyncio
import uuid
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from backend.decision_engine.decision_models import RiskLevel

class ConfirmationStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"

class ConfirmationRequest:
    def __init__(
        self,
        task_id: str,
        step_number: int,
        action_description: str,
        risk_level: RiskLevel,
        reason: str,
        target_id: Optional[str] = None
    ):
        self.id = f"conf_{uuid.uuid4().hex[:8]}"
        self.task_id = task_id
        self.step_number = step_number
        self.action_description = action_description
        self.risk_level = risk_level
        self.reason = reason
        self.target_id = target_id
        self.status = ConfirmationStatus.PENDING
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.resolved_at: Optional[str] = None
        self.future: asyncio.Future = asyncio.get_running_loop().create_future()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "step_number": self.step_number,
            "action_description": self.action_description,
            "risk_level": self.risk_level.value,
            "reason": self.reason,
            "target_id": self.target_id,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }

class ConfirmationManager:
    """
    Coordinates asynchronous human-in-the-loop approvals.
    """

    def __init__(self):
        self.pending_requests: Dict[str, ConfirmationRequest] = {}

    def create_request(
        self,
        task_id: str,
        step_number: int,
        action_description: str,
        risk_level: RiskLevel,
        reason: str,
        target_id: Optional[str] = None
    ) -> ConfirmationRequest:
        req = ConfirmationRequest(
            task_id=task_id,
            step_number=step_number,
            action_description=action_description,
            risk_level=risk_level,
            reason=reason,
            target_id=target_id
        )
        self.pending_requests[req.id] = req
        return req

    async def wait_for_decision(self, request_id: str, timeout_seconds: float = 300.0) -> bool:
        """Wait for human user to approve or reject the request."""
        req = self.pending_requests.get(request_id)
        if not req:
            return False

        try:
            approved = await asyncio.wait_for(req.future, timeout=timeout_seconds)
            return approved
        except asyncio.TimeoutError:
            req.status = ConfirmationStatus.TIMED_OUT
            req.resolved_at = datetime.now(timezone.utc).isoformat()
            return False

    def resolve(self, request_id: str, approved: bool) -> bool:
        """Resolve a pending confirmation by user interaction."""
        req = self.pending_requests.get(request_id)
        if not req or req.status != ConfirmationStatus.PENDING:
            return False

        req.status = ConfirmationStatus.APPROVED if approved else ConfirmationStatus.REJECTED
        req.resolved_at = datetime.now(timezone.utc).isoformat()

        if not req.future.done():
            req.future.set_result(approved)
        return True

    def get_pending_for_task(self, task_id: str) -> Optional[ConfirmationRequest]:
        for req in self.pending_requests.values():
            if req.task_id == task_id and req.status == ConfirmationStatus.PENDING:
                return req
        return None
