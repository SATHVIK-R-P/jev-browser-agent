import os
import sys
import uvicorn
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings

def main():
    host = os.getenv("HOST", settings.HOST)
    port = int(os.getenv("PORT", settings.PORT))

    # Ensure stdout handles UTF-8 on Windows cp1252 consoles
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 60)
    print(">> Starting JEV Browser Agent -- Autonomous Web Task Executor")
    print(f"[*] Server: http://{host}:{port}")
    print(f"[*] JEV Mode: {settings.JEV_MODE.upper()}")
    print(f"[*] Fallback LLM: {settings.LLM_PROVIDER}")
    print(f"[*] Thresholds: Auto >= {settings.AUTO_EXECUTE_THRESHOLD} | Low-Risk >= {settings.LOW_RISK_THRESHOLD}")
    print("=" * 60)

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
