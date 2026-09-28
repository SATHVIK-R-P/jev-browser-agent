import os
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # JEV Configuration
    JEV_MODE: str = Field(default="mock", description="JEV mode: 'mock' or 'real'")
    JEV_API_KEY: str = Field(default="", description="JEV API key")
    JEV_API_URL: str = Field(default="https://api.jev.ai/v1", description="JEV API base URL")
    JEV_MODEL: str = Field(default="system-one-v1", description="JEV model identifier")
    JEV_TIMEOUT_SECONDS: float = Field(default=10.0, description="JEV HTTP timeout")

    # Fallback LLM Configuration
    LLM_PROVIDER: str = Field(default="mock", description="LLM provider: 'mock', 'openai-compatible', 'gemini'")
    LLM_API_KEY: str = Field(default="", description="LLM API key")
    LLM_BASE_URL: str = Field(default="https://api.openai.com/v1", description="OpenAI-compatible base URL")
    LLM_MODEL: str = Field(default="gpt-4o-mini", description="LLM model identifier")
    LLM_TIMEOUT_SECONDS: float = Field(default=15.0, description="LLM HTTP timeout")

    # Confidence Thresholds
    AUTO_EXECUTE_THRESHOLD: float = Field(default=0.90, description=">= 0.90 executes immediately")
    LOW_RISK_THRESHOLD: float = Field(default=0.70, description="0.70-0.89 executes only if LOW risk")

    # Browser & Execution
    HEADLESS: bool = Field(default=True, description="Run Playwright in headless mode")
    BROWSER_TIMEOUT_MS: int = Field(default=30000, description="Browser action timeout")
    ACTION_DELAY_MS: int = Field(default=500, description="Delay between actions for observation")
    MAX_STEPS: int = Field(default=30, description="Max allowed execution steps per task")
    CAPTURE_SCREENSHOTS: bool = Field(default=True, description="Capture live page screenshots")

    # Server & Storage
    HOST: str = Field(default="0.0.0.0", description="Server listen host")
    PORT: int = Field(default=8000, description="Server listen port")
    DB_PATH: str = Field(default="data/jev_agent.db", description="SQLite database path")
    SCREENSHOTS_DIR: str = Field(default="data/screenshots", description="Directory for saving screenshots")

    def load_yaml_overrides(self, yaml_path: Optional[Path] = None) -> None:
        """Allow config.yaml to override defaults if env vars are not set."""
        path = yaml_path or (BASE_DIR / "config.yaml")
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = yaml.safe_load(f) or {}

            if "jev" in data:
                jev = data["jev"]
                if "mode" in jev and not os.getenv("JEV_MODE"):
                    self.JEV_MODE = jev["mode"]
                if "api_key" in jev and not os.getenv("JEV_API_KEY") and jev["api_key"]:
                    self.JEV_API_KEY = jev["api_key"]
                if "api_url" in jev and not os.getenv("JEV_API_URL"):
                    self.JEV_API_URL = jev["api_url"]
                if "model" in jev and not os.getenv("JEV_MODEL"):
                    self.JEV_MODEL = jev["model"]
                if "timeout_seconds" in jev and not os.getenv("JEV_TIMEOUT_SECONDS"):
                    self.JEV_TIMEOUT_SECONDS = float(jev["timeout_seconds"])

            if "llm" in data:
                llm = data["llm"]
                if "provider" in llm and not os.getenv("LLM_PROVIDER"):
                    self.LLM_PROVIDER = llm["provider"]
                if "api_key" in llm and not os.getenv("LLM_API_KEY") and llm["api_key"]:
                    self.LLM_API_KEY = llm["api_key"]
                if "base_url" in llm and not os.getenv("LLM_BASE_URL"):
                    self.LLM_BASE_URL = llm["base_url"]
                if "model" in llm and not os.getenv("LLM_MODEL"):
                    self.LLM_MODEL = llm["model"]

            if "confidence_thresholds" in data:
                ct = data["confidence_thresholds"]
                if "auto_execute" in ct and not os.getenv("AUTO_EXECUTE_THRESHOLD"):
                    self.AUTO_EXECUTE_THRESHOLD = float(ct["auto_execute"])
                if "low_risk" in ct and not os.getenv("LOW_RISK_THRESHOLD"):
                    self.LOW_RISK_THRESHOLD = float(ct["low_risk"])

            if "browser" in data:
                br = data["browser"]
                if "headless" in br and not os.getenv("HEADLESS"):
                    self.HEADLESS = bool(br["headless"])
                if "timeout_ms" in br and not os.getenv("BROWSER_TIMEOUT_MS"):
                    self.BROWSER_TIMEOUT_MS = int(br["timeout_ms"])

            if "agent" in data:
                ag = data["agent"]
                if "max_steps" in ag and not os.getenv("MAX_STEPS"):
                    self.MAX_STEPS = int(ag["max_steps"])
                if "action_delay_ms" in ag and not os.getenv("ACTION_DELAY_MS"):
                    self.ACTION_DELAY_MS = int(ag["action_delay_ms"])

            if "server" in data:
                srv = data["server"]
                if "host" in srv and not os.getenv("HOST"):
                    self.HOST = srv["host"]
                if "port" in srv and not os.getenv("PORT"):
                    self.PORT = int(srv["port"])
                if "db_path" in srv and not os.getenv("DB_PATH"):
                    self.DB_PATH = srv["db_path"]
        except Exception:
            pass

    def get_public_config(self) -> Dict[str, Any]:
        """Return safe config representation for UI without exposing keys."""
        return {
            "jev_mode": self.JEV_MODE,
            "jev_model": self.JEV_MODEL,
            "jev_has_key": bool(self.JEV_API_KEY),
            "llm_provider": self.LLM_PROVIDER,
            "llm_model": self.LLM_MODEL,
            "llm_has_key": bool(self.LLM_API_KEY),
            "auto_execute_threshold": self.AUTO_EXECUTE_THRESHOLD,
            "low_risk_threshold": self.LOW_RISK_THRESHOLD,
            "max_steps": self.MAX_STEPS,
            "headless": self.HEADLESS,
            "action_delay_ms": self.ACTION_DELAY_MS,
        }

settings = Settings()
settings.load_yaml_overrides()
