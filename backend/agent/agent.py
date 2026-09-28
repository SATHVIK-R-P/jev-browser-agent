import asyncio
import time
import logging
import uuid
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime, timezone

from backend.agent.task_state import TaskState, TaskStatus, AgentMetrics
from backend.agent.planner import Planner, TaskPlan
from backend.agent.observer import AgentObserver
from backend.agent.candidate_generator import CandidateGenerator
from backend.agent.decision_manager import DecisionManager
from backend.agent.verifier import Verifier
from backend.browser.browser_manager import BrowserManager
from backend.browser.action_executor import ActionExecutor
from backend.browser.page_state import PageState
from backend.decision_engine.decision_models import (
    DecisionRequest,
    DecisionResult,
    ActionType,
    CandidateAction,
    RiskLevel
)
from backend.safety.confirmation_manager import ConfirmationRequest
from backend.database.database import Database

logger = logging.getLogger(__name__)

class AgentEvent:
    TASK_STARTED = "TASK_STARTED"
    PAGE_OPENED = "PAGE_OPENED"
    PAGE_ANALYZED = "PAGE_ANALYZED"
    CANDIDATES_FOUND = "CANDIDATES_FOUND"
    JEV_DECISION = "JEV_DECISION"
    CONFIDENCE_RESULT = "CONFIDENCE_RESULT"
    ACTION_STARTED = "ACTION_STARTED"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    VERIFICATION = "VERIFICATION"
    LLM_FALLBACK = "LLM_FALLBACK"
    HUMAN_CONFIRMATION_REQUIRED = "HUMAN_CONFIRMATION_REQUIRED"
    TASK_PAUSED = "TASK_PAUSED"
    TASK_RESUMED = "TASK_RESUMED"
    TASK_STOPPED = "TASK_STOPPED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"

class BrowserAgent:
    """
    Main Autonomous Browser Agent loop executing the confidence-aware browser tasks.
    """

    def __init__(
        self,
        task_id: str,
        prompt: str,
        browser_manager: BrowserManager,
        decision_manager: DecisionManager,
        db: Database,
        max_steps: int = 30,
        action_delay_ms: int = 500,
        capture_screenshots: bool = True,
        event_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ):
        self.task_id = task_id
        self.prompt = prompt
        self.browser_manager = browser_manager
        self.decision_manager = decision_manager
        self.db = db
        self.max_steps = max_steps
        self.action_delay_ms = action_delay_ms
        self.capture_screenshots = capture_screenshots
        self.event_callback = event_callback

        self.state = TaskState(
            task_id=task_id,
            prompt=prompt,
            max_steps=max_steps,
            status=TaskStatus.PENDING
        )

        self.observer = AgentObserver()
        self.action_executor = ActionExecutor()
        self.plan: Optional[TaskPlan] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Unpaused initially
        self._stop_requested = False

    async def emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit real-time WebSocket / SSE telemetry event."""
        payload = {
            "type": event_type,
            "task_id": self.task_id,
            "step": self.state.current_step,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
            "metrics": self.state.metrics.to_display_dict(),
        }
        if self.event_callback:
            try:
                res = self.event_callback(payload)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as exc:
                logger.warning(f"Error in event callback: {exc}")

    def pause(self):
        """Pause agent execution loop."""
        self._pause_event.clear()
        self.state.status = TaskStatus.PAUSED
        asyncio.create_task(self.emit_event(AgentEvent.TASK_PAUSED, {"message": "Task paused by user"}))

    def resume(self):
        """Resume agent execution loop."""
        self.state.status = TaskStatus.RUNNING
        self._pause_event.set()
        asyncio.create_task(self.emit_event(AgentEvent.TASK_RESUMED, {"message": "Task resumed by user"}))

    def stop(self):
        """Stop agent execution loop."""
        self._stop_requested = True
        self._pause_event.set()
        self.state.status = TaskStatus.STOPPED

    async def run(self) -> TaskState:
        """
        Main execution loop:
        Observe -> Generate candidates -> Decision engine -> Confidence evaluation -> Safety evaluation -> Execute -> Verify -> Observe again -> Continue
        """
        logger.info(f"Starting agent task {self.task_id}: '{self.prompt}'")
        self.state.status = TaskStatus.RUNNING
        self.plan = Planner.create_plan(self.prompt)
        self.state.subgoals = self.plan.subgoals
        self.state.current_subgoal = self.plan.current_subgoal

        # Persist task start
        await self.db.save_task(self.task_id, self.prompt, self.max_steps, status="RUNNING")
        await self.emit_event(AgentEvent.TASK_STARTED, {
            "prompt": self.prompt,
            "plan": {
                "initial_url": self.plan.initial_url,
                "subgoals": self.plan.subgoals,
                "search_query": self.plan.search_query,
            }
        })

        page = None
        try:
            page = await self.browser_manager.start()

            # Execute Step 0: Open initial target URL
            await self.emit_event(AgentEvent.PAGE_OPENED, {"url": self.plan.initial_url})
            nav_ok, nav_msg = await self.action_executor.navigate(page, self.plan.initial_url)
            if not nav_ok:
                logger.warning(f"Initial navigation warning: {nav_msg}")

            while self.state.current_step < self.max_steps:
                # 1. Check Stop / Pause signals
                if self._stop_requested:
                    self.state.status = TaskStatus.STOPPED
                    await self.emit_event(AgentEvent.TASK_STOPPED, {"message": "Task stopped by user request."})
                    await self.db.update_task_status(self.task_id, "STOPPED", self.state.current_step, "Task stopped by user.")
                    return self.state

                await self._pause_event.wait()
                self.state.current_step += 1
                step_num = self.state.current_step
                step_id = f"step_{self.task_id}_{step_num}"
                self.state.metrics.steps_count = step_num

                # 2. Observe current webpage state
                pre_state = await self.observer.observe_page(
                    page=page,
                    task_id=self.task_id,
                    step_number=step_num,
                    capture_screenshots=self.capture_screenshots
                )

                await self.db.log_observation(
                    obs_id=f"obs_{uuid.uuid4().hex[:8]}",
                    task_id=self.task_id,
                    step_number=step_num,
                    url=pre_state.url,
                    title=pre_state.title,
                    element_count=len(pre_state.elements),
                    screenshot_path=f"data/screenshots/{self.task_id}_step_{step_num}.jpg" if self.capture_screenshots else None
                )

                await self.emit_event(AgentEvent.PAGE_ANALYZED, {
                    "url": pre_state.url,
                    "title": pre_state.title,
                    "element_count": len(pre_state.elements),
                    "elements_sample": [e.to_summary() for e in pre_state.elements[:8]],
                    "screenshot": pre_state.screenshot_base64
                })

                # 3. Generate candidate actions
                candidates = CandidateGenerator.generate_candidates(
                    page_state=pre_state,
                    task_goal=self.prompt,
                    current_subgoal=self.plan.current_subgoal,
                    search_query=self.plan.search_query,
                    recent_actions=self.state.recent_actions,
                    initial_url=self.plan.initial_url
                )

                # Persist candidates to SQLite
                await self.db.log_candidate_actions(
                    cand_id=f"cand_rec_{uuid.uuid4().hex[:8]}",
                    task_id=self.task_id,
                    step_number=step_num,
                    candidates_data=[c.to_display_dict() for c in candidates]
                )

                await self.emit_event(AgentEvent.CANDIDATES_FOUND, {
                    "count": len(candidates),
                    "candidates": [c.to_display_dict() for c in candidates]
                })

                # 4. Decision Engine & Confidence Evaluation
                decision_req = DecisionRequest(
                    task_id=self.task_id,
                    step_number=step_num,
                    task_goal=self.prompt,
                    current_subgoal=self.plan.current_subgoal,
                    page_url=pre_state.url,
                    page_title=pre_state.title,
                    candidates=candidates,
                    recent_actions=self.state.recent_actions
                )

                def on_human_callback(conf_req: ConfirmationRequest, dec: DecisionResult):
                    self.state.status = TaskStatus.WAITING_APPROVAL
                    self.state.pending_approval = conf_req.to_dict()
                    asyncio.create_task(self.emit_event(AgentEvent.HUMAN_CONFIRMATION_REQUIRED, {
                        "confirmation_id": conf_req.id,
                        "action": conf_req.action_description,
                        "risk_level": conf_req.risk_level.value,
                        "reason": conf_req.reason,
                        "target_id": conf_req.target_id
                    }))

                decision, route_note, human_approved = await self.decision_manager.get_and_authorize_decision(
                    decision_req,
                    on_human_required=on_human_callback
                )

                # Reset waiting approval status back to running if approved
                if self.state.status == TaskStatus.WAITING_APPROVAL:
                    self.state.status = TaskStatus.RUNNING
                    self.state.pending_approval = None

                self.state.latest_decision = decision
                self.state.metrics.confidences.append(decision.confidence)

                # Telemetry counts
                if "llm" in decision.provider.lower():
                    self.state.metrics.llm_fallbacks_count += 1
                    await self.emit_event(AgentEvent.LLM_FALLBACK, {
                        "provider": decision.provider,
                        "reason": decision.reason,
                        "confidence": decision.confidence
                    })
                elif "jev" in decision.provider.lower():
                    self.state.metrics.jev_decisions_count += 1
                    await self.emit_event(AgentEvent.JEV_DECISION, {
                        "decision": decision.decision,
                        "target_id": decision.target_id,
                        "confidence": decision.confidence,
                        "provider": decision.provider,
                        "reason": decision.reason
                    })

                if human_approved:
                    self.state.metrics.human_approvals_count += 1

                await self.emit_event(AgentEvent.CONFIDENCE_RESULT, {
                    "confidence": decision.confidence,
                    "risk_level": decision.risk_level.value,
                    "route_note": route_note
                })

                # Check if decision was FINISH
                if decision.decision.lower() == ActionType.FINISH.value:
                    self.state.status = TaskStatus.COMPLETED
                    self.state.result_summary = f"Task completed successfully: {decision.reason}"
                    await self.emit_event(AgentEvent.TASK_COMPLETED, {
                        "summary": self.state.result_summary,
                        "steps": step_num
                    })
                    await self.db.update_task_status(self.task_id, "COMPLETED", step_num, self.state.result_summary)
                    return self.state

                # 5. Execute Action
                await self.emit_event(AgentEvent.ACTION_STARTED, {
                    "action": decision.decision,
                    "target_id": decision.target_id,
                    "value": decision.value,
                    "description": decision.reason
                })

                target_elem = pre_state.get_element_by_id(decision.target_id) if decision.target_id else None
                action_start_t = time.time()
                success = False
                action_msg = ""

                action_type = decision.decision.lower()
                if action_type == ActionType.CLICK.value:
                    success, action_msg = await self.action_executor.click(
                        page=page,
                        element=target_elem,
                        selector=decision.target_selector
                    )
                elif action_type == ActionType.TYPE.value:
                    val = decision.value or self.plan.search_query or self.prompt
                    success, action_msg = await self.action_executor.type_text(
                        page=page,
                        text=val,
                        element=target_elem,
                        selector=decision.target_selector,
                        press_enter=True
                    )
                elif action_type == ActionType.NAVIGATE.value:
                    nav_url = decision.value or self.plan.initial_url
                    success, action_msg = await self.action_executor.navigate(page, nav_url)
                elif action_type == ActionType.SCROLL.value:
                    amt = int(decision.value or 500)
                    success, action_msg = await self.action_executor.scroll(page, direction="down", amount=amt)
                elif action_type == ActionType.WAIT.value:
                    success, action_msg = await self.action_executor.wait(page, 1500)
                else:
                    success, action_msg = await self.action_executor.wait(page, 500)

                action_lat_ms = (time.time() - action_start_t) * 1000
                self.state.metrics.total_action_latency_ms += action_lat_ms
                if success:
                    self.state.metrics.successful_actions_count += 1
                else:
                    self.state.metrics.failed_actions_count += 1

                self.state.recent_actions.append(f"Step {step_num}: {action_msg}")

                await self.emit_event(AgentEvent.ACTION_COMPLETED, {
                    "success": success,
                    "message": action_msg,
                    "latency_ms": round(action_lat_ms, 1)
                })

                # Delay for browser stability & observer clarity
                if self.action_delay_ms > 0:
                    await asyncio.sleep(self.action_delay_ms / 1000.0)

                # 6. Verify Result (Observe new state)
                post_state = await self.observer.observe_page(
                    page=page,
                    task_id=self.task_id,
                    step_number=step_num,
                    capture_screenshots=self.capture_screenshots
                )

                v_ok, v_msg, is_completed = Verifier.verify_action_effect(
                    pre_state=pre_state,
                    post_state=post_state,
                    decision=decision,
                    task_goal=self.prompt
                )

                await self.db.log_action_result(
                    res_id=f"res_{uuid.uuid4().hex[:8]}",
                    task_id=self.task_id,
                    step_number=step_num,
                    success=success,
                    message=action_msg,
                    latency_ms=action_lat_ms,
                    verification_result=v_msg
                )

                await self.emit_event(AgentEvent.VERIFICATION, {
                    "verified": v_ok,
                    "message": v_msg,
                    "is_completed": is_completed,
                    "screenshot": post_state.screenshot_base64
                })

                if is_completed:
                    self.state.status = TaskStatus.COMPLETED
                    self.state.result_summary = f"Task completed: {v_msg}"
                    await self.emit_event(AgentEvent.TASK_COMPLETED, {
                        "summary": self.state.result_summary,
                        "steps": step_num
                    })
                    await self.db.update_task_status(self.task_id, "COMPLETED", step_num, self.state.result_summary)
                    return self.state

                # Advance plan subgoal if verified
                if v_ok:
                    self.plan.advance_subgoal()
                    self.state.current_subgoal = self.plan.current_subgoal

            # Loop reached MAX_STEPS
            self.state.status = TaskStatus.COMPLETED
            self.state.result_summary = f"Reached maximum configured step limit ({self.max_steps} steps)."
            await self.emit_event(AgentEvent.TASK_COMPLETED, {
                "summary": self.state.result_summary,
                "steps": self.max_steps
            })
            await self.db.update_task_status(self.task_id, "COMPLETED", self.max_steps, self.state.result_summary)
            return self.state

        except Exception as exc:
            logger.exception(f"Unhandled error in agent loop: {exc}")
            self.state.status = TaskStatus.FAILED
            self.state.error = str(exc)
            await self.emit_event(AgentEvent.TASK_FAILED, {"error": str(exc)})
            await self.db.update_task_status(self.task_id, "FAILED", self.state.current_step, error_message=str(exc))
            return self.state

        finally:
            # We keep the browser alive during the task lifecycle; cleanup can be triggered on shutdown
            pass
