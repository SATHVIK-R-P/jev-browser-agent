import os
from pathlib import Path
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.api.tasks import router as api_router
from backend.api.websocket import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("jev_browser_agent")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("JEV Browser Agent — Autonomous Web Task Executor")
    logger.info(f"Mode: {settings.JEV_MODE.upper()} JEV MODE")
    logger.info(f"Thresholds: Auto-Execute >= {settings.AUTO_EXECUTE_THRESHOLD}, Low-Risk >= {settings.LOW_RISK_THRESHOLD}")
    logger.info(f"Headless Browser: {settings.HEADLESS}")
    logger.info("=" * 60)
    await api_router_startup()
    yield
    logger.info("Shutting down JEV Browser Agent...")

async def api_router_startup():
    from backend.api.tasks import db
    await db.init_db()

app = FastAPI(
    title="JEV Browser Agent — Autonomous Web Task Executor",
    version="1.0.0",
    description="Confidence-aware autonomous browser agent powered by JEV System-One decision capability with LLM fallback and human safety layer.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")

# WebSocket Endpoint
@app.websocket("/ws")
@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str = "global"):
    await manager.connect(websocket, task_id)
    try:
        while True:
            # Keep alive and receive client control messages if any
            data = await websocket.receive_text()
            logger.debug(f"Received from client ({task_id}): {data}")
    except WebSocketDisconnect:
        await manager.disconnect(websocket, task_id)
    except Exception as exc:
        logger.warning(f"WebSocket error ({task_id}): {exc}")
        await manager.disconnect(websocket, task_id)

# Frontend Static Files
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if DATA_DIR.exists():
    # Mount screenshots directory if exists
    screenshots_path = DATA_DIR / "screenshots"
    screenshots_path.mkdir(parents=True, exist_ok=True)
    app.mount("/data/screenshots", StaticFiles(directory=str(screenshots_path)), name="screenshots")

@app.get("/", include_in_schema=False)
async def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "JEV Browser Agent Backend Running. Frontend not found."}


