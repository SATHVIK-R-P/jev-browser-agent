import time
import logging
from typing import Optional, Tuple, Dict, Any, Callable
from backend.decision_engine.decision_models import DecisionRequest, DecisionResult, RiskLevel, ActionType
from backend.decision_engine.decision_router import DecisionRouter
from backend.safety.confirmation_manager import ConfirmationManager, ConfirmationRequest, ConfirmationStatus
from backend.safety.permission_manager import PermissionManager
from backend.database.database import Database

logger = logging.getLogger(__name__)

class DecisionManager:
    """
    Coordinates decision routing, safety permissions, human approval interrupts,
    and database telemetry logging.
    """

    def __init__(
        self,
        router: DecisionRouter,
        confirmation_manager: ConfirmationManager,
        permission_manager: PermissionManager,
        db: Database
    ):
        self.router = router
        self.confirmation_manager = confirmation_manager
        self.permission_manager = permission_manager
        self.db = db

    async def get_and_authorize_decision(
        self,
        request: DecisionRequest,
        on_human_required: Optional[Callable[[ConfirmationRequest, DecisionResult], Any]] = None
    ) -> Tuple[DecisionResult, str, bool]:
        """
        Executes decision routing and enforces human-in-the-loop confirmation if needed.
        Returns: (DecisionResult, routing_note: str, human_approved: bool).
        """
        t0 = time.time()
        decision, route_note = await self.router.route_decision(request)
        decision_latency_ms = (time.time() - t0) * 1000

        # Check safety permissions
        permitted, perm_msg = self.permission_manager.is_execution_permitted(decision)
        human_approved = False

        if not permitted or decision.requires_human:
            logger.info(f"Action '{decision.decision}' requires human approval ({perm_msg})")
            # Create human confirmation request
            conf_req = self.confirmation_manager.create_request(
                task_id=request.task_id,
                step_number=request.step_number,
                action_description=f"{decision.decision.upper()} {decision.target_id or ''} - {decision.reason}",
                risk_level=decision.risk_level,
                reason=perm_msg,
                target_id=decision.target_id
            )

            # Persist pending approval to SQLite
            await self.db.log_approval(
                approval_id=conf_req.id,
                task_id=request.task_id,
                step_number=request.step_number,
                action_description=conf_req.action_description,
                risk_level=conf_req.risk_level.value,
                status=conf_req.status,
                requested_at=conf_req.created_at
            )

            # Fire callback (e.g. notify websocket)
            if on_human_required:
                on_human_required(conf_req, decision)

            # Wait for user approval or rejection
            approved = await self.confirmation_manager.wait_for_decision(conf_req.id, timeout_seconds=300.0)
            human_approved = approved

            # Update DB with final resolution
            await self.db.log_approval(
                approval_id=conf_req.id,
                task_id=request.task_id,
                step_number=request.step_number,
                action_description=conf_req.action_description,
                risk_level=conf_req.risk_level.value,
                status=conf_req.status,
                requested_at=conf_req.created_at,
                decided_at=conf_req.resolved_at
            )

            if not approved:
                route_note += " [REJECTED by human supervisor]"
                # Substitute with wait / finish
                decision = DecisionResult(
                    decision=ActionType.WAIT.value,
                    confidence=1.0,
                    reason="Action rejected by user. Waiting for next step or user instruction.",
                    provider="human",
                    risk_level=RiskLevel.LOW
                )
            else:
                route_note += " [APPROVED by human supervisor]"
                decision.provider = f"{decision.provider}+human"

        # Log decision into SQLite
        await self.db.log_decision(
            decision_id=decision.decision_id,
            task_id=request.task_id,
            step_number=request.step_number,
            provider=decision.provider,
            action_type=decision.decision,
            target_id=decision.target_id,
            confidence=decision.confidence,
            reason=decision.reason,
            latency_ms=decision_latency_ms
        )

        return decision, route_note, human_approved
