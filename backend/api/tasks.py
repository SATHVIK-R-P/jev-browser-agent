import asyncio
import uuid
import json
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.config import settings
from backend.database.database import Database
from backend.browser.browser_manager import BrowserManager
from backend.decision_engine.jev_client import create_jev_client
from backend.decision_engine.fallback_llm import create_fallback_llm
from backend.decision_engine.confidence import ConfidenceEvaluator
from backend.decision_engine.decision_router import DecisionRouter
from backend.safety.risk_classifier import RiskClassifier
from backend.safety.permission_manager import PermissionManager
from backend.safety.confirmation_manager import ConfirmationManager
from backend.agent.decision_manager import DecisionManager
from backend.agent.agent import BrowserAgent
from backend.api.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter()

# Global instances
db = Database(db_path=settings.DB_PATH)
confirmation_manager = ConfirmationManager()
permission_manager = PermissionManager(
    auto_execute_threshold=settings.AUTO_EXECUTE_THRESHOLD,
    low_risk_threshold=settings.LOW_RISK_THRESHOLD
)

# Registry of active agent instances: task_id -> BrowserAgent
active_agents: Dict[str, BrowserAgent] = {}

class CreateTaskRequest(BaseModel):
    prompt: str = Field(..., description="Natural language web task to execute")
    max_steps: Optional[int] = Field(default=None, description="Max execution steps")

class ApprovalActionRequest(BaseModel):
    confirmation_id: Optional[str] = Field(default=None, description="Specific confirmation request ID")

# Database initialized via Database auto-initialization and lifespan

@router.get("/health", tags=["System"])
async def get_health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "JEV Browser Agent",
        "version": "1.0.0",
        "jev_mode": settings.JEV_MODE,
        "llm_provider": settings.LLM_PROVIDER,
        "active_tasks": len(active_agents),
    }

@router.get("/config", tags=["System"])
async def get_config():
    """Returns safe runtime configuration and confidence thresholds."""
    return settings.get_public_config()

@router.post("/tasks", tags=["Tasks"])
async def create_task(req: CreateTaskRequest, background_tasks: BackgroundTasks):
    """
    Creates and starts a new autonomous browser execution task.
    """
    clean_prompt = RiskClassifier.sanitize(req.prompt.strip())
    if not clean_prompt:
        raise HTTPException(status_code=400, detail="Task prompt cannot be empty.")

    task_id = f"task_{uuid.uuid4().hex[:10]}"
    max_steps = req.max_steps or settings.MAX_STEPS

    # Create JEV Client and Fallback LLM instances
    jev_client = create_jev_client(
        mode=settings.JEV_MODE,
        api_key=settings.JEV_API_KEY,
        api_url=settings.JEV_API_URL,
        model=settings.JEV_MODEL,
        timeout_seconds=settings.JEV_TIMEOUT_SECONDS
    )

    fallback_llm = create_fallback_llm(
        provider=settings.LLM_PROVIDER,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS
    )

    conf_evaluator = ConfidenceEvaluator(
        auto_execute_threshold=settings.AUTO_EXECUTE_THRESHOLD,
        low_risk_threshold=settings.LOW_RISK_THRESHOLD
    )

    decision_router = DecisionRouter(
        jev_client=jev_client,
        fallback_llm=fallback_llm,
        confidence_evaluator=conf_evaluator
    )

    dec_manager = DecisionManager(
        router=decision_router,
        confirmation_manager=confirmation_manager,
        permission_manager=permission_manager,
        db=db
    )

    browser_manager = BrowserManager(
        headless=settings.HEADLESS,
        timeout_ms=settings.BROWSER_TIMEOUT_MS
    )

    async def broadcast_callback(event_data: Dict[str, Any]):
        await manager.broadcast_event(event_data)

    agent = BrowserAgent(
        task_id=task_id,
        prompt=clean_prompt,
        browser_manager=browser_manager,
        decision_manager=dec_manager,
        db=db,
        max_steps=max_steps,
        action_delay_ms=settings.ACTION_DELAY_MS,
        capture_screenshots=settings.CAPTURE_SCREENSHOTS,
        event_callback=broadcast_callback
    )

    active_agents[task_id] = agent

    # Run agent in background
    async def run_agent_task():
        try:
            await agent.run()
        finally:
            await browser_manager.stop()

    background_tasks.add_task(run_agent_task)

    return {
        "task_id": task_id,
        "prompt": clean_prompt,
        "status": "RUNNING",
        "max_steps": max_steps,
        "jev_mode": settings.JEV_MODE,
    }

@router.get("/tasks/{task_id}", tags=["Tasks"])
async def get_task_details(task_id: str):
    """
    Fetches task status, steps, observations, decisions, and performance metrics.
    """
    # Check active memory state first
    agent = active_agents.get(task_id)
    if agent:
        db_data = await db.get_task(task_id) or {}
        return {
            "task_id": task_id,
            "prompt": agent.prompt,
            "status": agent.state.status.value,
            "current_step": agent.state.current_step,
            "max_steps": agent.max_steps,
            "current_subgoal": agent.state.current_subgoal,
            "metrics": agent.state.metrics.to_display_dict(),
            "latest_decision": agent.state.latest_decision.to_log_dict() if agent.state.latest_decision else None,
            "pending_approval": agent.state.pending_approval,
            "result_summary": agent.state.result_summary,
            "error": agent.state.error,
            "db_history": db_data
        }

    # Fallback to database
    db_data = await db.get_task(task_id)
    if not db_data:
        raise HTTPException(status_code=404, detail="Task not found.")
    return db_data

@router.post("/tasks/{task_id}/pause", tags=["Tasks"])
async def pause_task(task_id: str):
    """Pauses the execution loop of a running task."""
    agent = active_agents.get(task_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Active task not found.")
    agent.pause()
    await db.update_task_status(task_id, "PAUSED", agent.state.current_step)
    return {"task_id": task_id, "status": "PAUSED"}

@router.post("/tasks/{task_id}/resume", tags=["Tasks"])
async def resume_task(task_id: str):
    """Resumes a paused task."""
    agent = active_agents.get(task_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Active task not found.")
    agent.resume()
    await db.update_task_status(task_id, "RUNNING", agent.state.current_step)
    return {"task_id": task_id, "status": "RUNNING"}

@router.post("/tasks/{task_id}/stop", tags=["Tasks"])
async def stop_task(task_id: str):
    """Stops task execution permanently."""
    agent = active_agents.get(task_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Active task not found.")
    agent.stop()
    await db.update_task_status(task_id, "STOPPED", agent.state.current_step, "Stopped by user request.")
    return {"task_id": task_id, "status": "STOPPED"}

@router.post("/tasks/{task_id}/approve", tags=["Tasks"])
async def approve_task_action(task_id: str, req: Optional[ApprovalActionRequest] = None):
    """Human approval for a risky or low-confidence candidate action."""
    conf_req = None
    if req and req.confirmation_id:
        conf_req = confirmation_manager.pending_requests.get(req.confirmation_id)
    else:
        conf_req = confirmation_manager.get_pending_for_task(task_id)

    if not conf_req:
        raise HTTPException(status_code=400, detail="No pending confirmation found for this task.")

    success = confirmation_manager.resolve(conf_req.id, approved=True)
    return {"task_id": task_id, "confirmation_id": conf_req.id, "approved": success}

@router.post("/tasks/{task_id}/reject", tags=["Tasks"])
async def reject_task_action(task_id: str, req: Optional[ApprovalActionRequest] = None):
    """Human rejection for a candidate action."""
    conf_req = None
    if req and req.confirmation_id:
        conf_req = confirmation_manager.pending_requests.get(req.confirmation_id)
    else:
        conf_req = confirmation_manager.get_pending_for_task(task_id)

    if not conf_req:
        raise HTTPException(status_code=400, detail="No pending confirmation found for this task.")

    success = confirmation_manager.resolve(conf_req.id, approved=False)
    return {"task_id": task_id, "confirmation_id": conf_req.id, "rejected": success}

@router.get("/tasks/{task_id}/events", tags=["Tasks"])
async def get_task_events(task_id: str, request: Request):
    """
    Server-Sent Events (SSE) stream for real-time live events.
    """
    event_queue = manager.subscribe_sse(task_id)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield ": ping\n\n"
        finally:
            manager.unsubscribe_sse(task_id, event_queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
