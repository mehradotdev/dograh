from __future__ import annotations

from typing import Any

EXPECTED_STACKS = {
    "openai_realtime": {"realtime": ("openai_realtime", "gpt-realtime-2.1")},
    "gemini_live": {"realtime": ("google_realtime", "gemini-3.1-flash-live-preview")},
    "google_cascade": {
        "stt": ("google", "chirp_3"),
        "llm": ("google", "gemini-3.8-flash"),
        "tts": ("google", "wavenet"),
    },
}

EXPECTED_SETTINGS = {
    "google_cascade": {"stt_location": "eu"},
}


def validate_poc_runtime(engine: str | None, runtime: dict[str, Any]) -> None:
    if not engine:
        return
    expected = EXPECTED_STACKS.get(engine)
    if expected is None:
        raise ValueError(f"Unknown POC engine: {engine}")
    for section, pair in expected.items():
        got = (
            runtime.get(f"{section}_provider"),
            runtime.get(f"{section}_model"),
        )
        if got != pair:
            raise ValueError(
                f"POC {engine} requires {section}={pair[0]}/{pair[1]}; resolved {got[0]}/{got[1]}"
            )
    for field, expected_value in EXPECTED_SETTINGS.get(engine, {}).items():
        got = runtime.get(field)
        if got != expected_value:
            raise ValueError(
                f"POC {engine} requires {field}={expected_value}; resolved {got}"
            )
