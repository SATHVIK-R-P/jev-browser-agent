import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import aiosqlite
from backend.safety.risk_classifier import RiskClassifier

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    max_steps INTEGER NOT NULL,
    current_step INTEGER DEFAULT 0,
    result_summary TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS task_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    state_summary TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS browser_observations (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    element_count INTEGER DEFAULT 0,
    screenshot_path TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS candidate_actions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    candidate_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    provider TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target_id TEXT,
    confidence REAL NOT NULL,
    reason TEXT,
    latency_ms REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS action_results (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    success INTEGER NOT NULL,
    message TEXT,
    latency_ms REAL,
    verification_result TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    action_description TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_task_steps ON task_steps(task_id, step_number);
CREATE INDEX IF NOT EXISTS idx_decisions ON decisions(task_id, step_number);
CREATE INDEX IF NOT EXISTS idx_observations ON browser_observations(task_id, step_number);
"""

class Database:
    """
    Asynchronous SQLite repository for task logs, decisions, and safety records.
    """

    def __init__(self, db_path: str = "data/jev_agent.db"):
        self.db_path = db_path
        self._ensure_dir()

    def _ensure_dir(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self):
        """Initializes tables and indexes."""
        self._ensure_dir()
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(CREATE_TABLES_SQL)
            await db.commit()
        logger.info(f"Initialized database schema at {self.db_path}")

    async def _ensure_initialized(self):
        self._ensure_dir()
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(CREATE_TABLES_SQL)
            await db.commit()

    async def save_task(self, task_id: str, prompt: str, max_steps: int, status: str = "PENDING"):
        await self._ensure_initialized()
        now = datetime.now(timezone.utc).isoformat()
        clean_prompt = RiskClassifier.sanitize(prompt)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO tasks (id, prompt, status, max_steps, current_step, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (task_id, clean_prompt, status, max_steps, now, now)
            )
            await db.commit()

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        current_step: Optional[int] = None,
        result_summary: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        clean_summary = RiskClassifier.sanitize(result_summary) if result_summary else None
        clean_error = RiskClassifier.sanitize(error_message) if error_message else None
        completed_at = now if status in ["COMPLETED", "FAILED", "STOPPED"] else None

        async with aiosqlite.connect(self.db_path) as db:
            if current_step is not None:
                await db.execute(
                    """
                    UPDATE tasks
                    SET status=?, current_step=?, result_summary=COALESCE(?, result_summary),
                        error_message=COALESCE(?, error_message), updated_at=?,
                        completed_at=COALESCE(?, completed_at)
                    WHERE id=?
                    """,
                    (status, current_step, clean_summary, clean_error, now, completed_at, task_id)
                )
            else:
                await db.execute(
                    """
                    UPDATE tasks
                    SET status=?, result_summary=COALESCE(?, result_summary),
                        error_message=COALESCE(?, error_message), updated_at=?,
                        completed_at=COALESCE(?, completed_at)
                    WHERE id=?
                    """,
                    (status, clean_summary, clean_error, now, completed_at, task_id)
                )
            await db.commit()

    async def log_step(self, step_id: str, task_id: str, step_number: int, state_summary: str):
        now = datetime.now(timezone.utc).isoformat()
        clean_summary = RiskClassifier.sanitize(state_summary)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO task_steps (id, task_id, step_number, state_summary, created_at) VALUES (?, ?, ?, ?, ?)",
                (step_id, task_id, step_number, clean_summary, now)
            )
            await db.commit()

    async def log_observation(
        self,
        obs_id: str,
        task_id: str,
        step_number: int,
        url: str,
        title: Optional[str],
        element_count: int,
        screenshot_path: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        clean_url = RiskClassifier.sanitize(url)
        clean_title = RiskClassifier.sanitize(title) if title else ""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO browser_observations (id, task_id, step_number, url, title, element_count, screenshot_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (obs_id, task_id, step_number, clean_url, clean_title, element_count, screenshot_path, now)
            )
            await db.commit()

    async def log_candidate_actions(self, cand_id: str, task_id: str, step_number: int, candidates_data: List[Dict[str, Any]]):
        now = datetime.now(timezone.utc).isoformat()
        # Sanitize candidate json
        cand_str = RiskClassifier.sanitize(json.dumps(candidates_data))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO candidate_actions (id, task_id, step_number, candidate_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (cand_id, task_id, step_number, cand_str, now)
            )
            await db.commit()

    async def log_decision(
        self,
        decision_id: str,
        task_id: str,
        step_number: int,
        provider: str,
        action_type: str,
        target_id: Optional[str],
        confidence: float,
        reason: str,
        latency_ms: Optional[float] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        clean_reason = RiskClassifier.sanitize(reason)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO decisions (id, task_id, step_number, provider, action_type, target_id, confidence, reason, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (decision_id, task_id, step_number, provider, action_type, target_id, confidence, clean_reason, latency_ms, now)
            )
            await db.commit()

    async def log_action_result(
        self,
        res_id: str,
        task_id: str,
        step_number: int,
        success: bool,
        message: str,
        latency_ms: Optional[float] = None,
        verification_result: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        clean_msg = RiskClassifier.sanitize(message)
        clean_ver = RiskClassifier.sanitize(verification_result) if verification_result else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO action_results (id, task_id, step_number, success, message, latency_ms, verification_result, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (res_id, task_id, step_number, 1 if success else 0, clean_msg, latency_ms, clean_ver, now)
            )
            await db.commit()

    async def log_approval(
        self,
        approval_id: str,
        task_id: str,
        step_number: int,
        action_description: str,
        risk_level: str,
        status: str,
        requested_at: str,
        decided_at: Optional[str] = None
    ):
        clean_desc = RiskClassifier.sanitize(action_description)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO approvals (id, task_id, step_number, action_description, risk_level, status, requested_at, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    decided_at=excluded.decided_at
                """,
                (approval_id, task_id, step_number, clean_desc, risk_level, status, requested_at, decided_at)
            )
            await db.commit()

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                task_data = dict(row)

            # Retrieve recent steps and decisions
            async with db.execute(
                "SELECT * FROM decisions WHERE task_id = ? ORDER BY step_number ASC", (task_id,)
            ) as cursor:
                task_data["decisions"] = [dict(r) for r in await cursor.fetchall()]

            async with db.execute(
                "SELECT * FROM action_results WHERE task_id = ? ORDER BY step_number ASC", (task_id,)
            ) as cursor:
                task_data["action_results"] = [dict(r) for r in await cursor.fetchall()]

            async with db.execute(
                "SELECT * FROM browser_observations WHERE task_id = ? ORDER BY step_number ASC", (task_id,)
            ) as cursor:
                task_data["observations"] = [dict(r) for r in await cursor.fetchall()]

            async with db.execute(
                "SELECT * FROM approvals WHERE task_id = ? ORDER BY step_number ASC", (task_id,)
            ) as cursor:
                task_data["approvals"] = [dict(r) for r in await cursor.fetchall()]

            return task_data

    async def list_recent_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
                return [dict(r) for r in await cursor.fetchall()]
