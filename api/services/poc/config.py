from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PocSettings:
    wfms_base_url: str = os.getenv("WFMS_BASE_URL", "https://wfms.htistelecom.in")
    wfms_mode: str = os.getenv("POC_WFMS_MODE", "mock").lower()
    wfms_timeout_seconds: float = float(os.getenv("POC_WFMS_TIMEOUT_SECONDS", "5"))
    allow_unknown_caller_create: bool = (
        os.getenv("POC_WFMS_UNKNOWN_CALLER_CREATE_ENABLED", "true").lower() == "true"
    )
    recordings_dir: Path = Path(
        os.getenv(
            "POC_ASTERISK_RECORDINGS_DIR",
            "/srv/data/apps/ai-receptionist-poc/recordings",
        )
    )


SETTINGS = PocSettings()

POC_ENGINES = {
    "openai_realtime": {
        "label": "OpenAI Realtime",
        "enabled_env": "POC_OPENAI_ENABLED",
        "default_enabled": True,
        "limit_env": "POC_OPENAI_DAILY_LIMIT",
        "default_limit": 20,
    },
    "gemini_live": {
        "label": "Gemini Live",
        "enabled_env": "POC_GEMINI_ENABLED",
        "default_enabled": False,
        "limit_env": "POC_GEMINI_DAILY_LIMIT",
        "default_limit": 0,
    },
    "google_cascade": {
        "label": "Google Cascade",
        "enabled_env": "POC_GOOGLE_CASCADE_ENABLED",
        "default_enabled": False,
        "limit_env": "POC_GOOGLE_CASCADE_DAILY_LIMIT",
        "default_limit": 0,
    },
}


def engine_enabled(engine: str) -> bool:
    config = POC_ENGINES.get(engine)
    if not config:
        return False
    default = "true" if config["default_enabled"] else "false"
    return os.getenv(config["enabled_env"], default).lower() == "true"


def engine_daily_limit(engine: str) -> int:
    config = POC_ENGINES[engine]
    return max(0, int(os.getenv(config["limit_env"], str(config["default_limit"]))))
