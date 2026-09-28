import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app

@pytest.mark.asyncio
async def test_health_and_config_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        res = await client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "jev_mode" in data

        # Config check
        res_cfg = await client.get("/api/config")
        assert res_cfg.status_code == 200
        cfg_data = res_cfg.json()
        assert "auto_execute_threshold" in cfg_data
        assert "low_risk_threshold" in cfg_data
        assert cfg_data["auto_execute_threshold"] == 0.90

@pytest.mark.asyncio
async def test_task_creation_and_controls():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create task
        res = await client.post("/api/tasks", json={
            "prompt": "Open Wikipedia and search for artificial intelligence.",
            "max_steps": 5
        })
        assert res.status_code == 200
        task_data = res.json()
        task_id = task_data["task_id"]
        assert task_id.startswith("task_")
        assert task_data["status"] == "RUNNING"

        # Check task details
        res_get = await client.get(f"/api/tasks/{task_id}")
        assert res_get.status_code == 200
        details = res_get.json()
        assert details["task_id"] == task_id

        # Pause task
        res_pause = await client.post(f"/api/tasks/{task_id}/pause")
        assert res_pause.status_code == 200
        assert res_pause.json()["status"] == "PAUSED"

        # Resume task
        res_resume = await client.post(f"/api/tasks/{task_id}/resume")
        assert res_resume.status_code == 200
        assert res_resume.json()["status"] == "RUNNING"

        # Stop task
        res_stop = await client.post(f"/api/tasks/{task_id}/stop")
        assert res_stop.status_code == 200
        assert res_stop.json()["status"] == "STOPPED"
