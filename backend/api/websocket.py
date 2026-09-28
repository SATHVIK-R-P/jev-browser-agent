import asyncio
import json
import logging
from typing import Dict, List, Set, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages active WebSocket connections and handles real-time event broadcasting.
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.task_subscribers: Dict[str, Set[WebSocket]] = {}
        self.task_event_queues: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, task_id: str = "global"):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
            if task_id not in self.task_subscribers:
                self.task_subscribers[task_id] = set()
            self.task_subscribers[task_id].add(websocket)
        logger.info(f"WebSocket client connected to task '{task_id}'. Total clients: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket, task_id: str = "global"):
        async with self._lock:
            self.active_connections.discard(websocket)
            if task_id in self.task_subscribers:
                self.task_subscribers[task_id].discard(websocket)
        logger.info(f"WebSocket client disconnected from task '{task_id}'.")

    async def broadcast_event(self, event_payload: Dict[str, Any]):
        """Broadcasts event to task-specific and global listeners."""
        task_id = event_payload.get("task_id", "global")
        msg_str = json.dumps(event_payload)

        # Notify any registered SSE queues
        if task_id in self.task_event_queues:
            for q in list(self.task_event_queues[task_id]):
                try:
                    q.put_nowait(event_payload)
                except Exception:
                    pass

        # Collect targets
        async with self._lock:
            recipients = set(self.task_subscribers.get(task_id, set()))
            recipients.update(self.task_subscribers.get("global", set()))
            recipients.update(self.active_connections)

        dead_connections = []
        for ws in recipients:
            try:
                await ws.send_text(msg_str)
            except Exception:
                dead_connections.append(ws)

        if dead_connections:
            async with self._lock:
                for dead_ws in dead_connections:
                    self.active_connections.discard(dead_ws)
                    for subs in self.task_subscribers.values():
                        subs.discard(dead_ws)

    def subscribe_sse(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        if task_id not in self.task_event_queues:
            self.task_event_queues[task_id] = []
        self.task_event_queues[task_id].append(q)
        return q

    def unsubscribe_sse(self, task_id: str, q: asyncio.Queue):
        if task_id in self.task_event_queues:
            if q in self.task_event_queues[task_id]:
                self.task_event_queues[task_id].remove(q)

manager = ConnectionManager()
