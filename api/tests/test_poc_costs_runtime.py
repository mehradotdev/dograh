import pytest

from api.services.poc.config import engine_daily_limit, engine_enabled
from api.services.poc.costs import calculate_poc_cost, summarize_latency
from api.services.poc.runtime import validate_poc_runtime


def test_google_cascade_cost_is_componentized():
    result = calculate_poc_cost(
        "google_cascade",
        {
            "llm": {
                "Google|||gemini-3.8-flash": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 200,
                    "total_tokens": 1200,
                }
            },
            "stt": {"Google|||latest_short": 60.0},
            "tts": {"Google|||wavenet": 1000},
            "call_duration_seconds": 60,
        },
    )
    assert result["estimated_total"] > 0.016
    assert result["normalized_list_cost_usd"] == result["estimated_total"]
    assert result["actual_billed_estimate_usd"] == result["estimated_total"]
    assert result["pricing_version"] == "2026-09-09"
    assert result["pricing_as_of"] == "2026-09-09"
    assert len(result["components"]) == 4
    assert all(component["quantity_source"] for component in result["components"])


def test_latency_summary_keeps_first_response_turns_and_wfms_timings():
    result = summarize_latency(
        [
            {"type": "ttfb_metric", "payload": {"ttfb_seconds": 0.42}},
            {"type": "latency_measured", "payload": {"latency_seconds": 0.65}},
        ],
        [{"latency_ms": 80, "wfms": {"latency_ms": 75}}],
    )
    assert result["time_to_first_response_ms"] == 420
    assert result["turn_response_ms"] == [650.0]
    assert result["wfms_api_ms"] == [75.0]


def test_runtime_rejects_silent_model_substitution():
    with pytest.raises(ValueError, match="requires realtime"):
        validate_poc_runtime(
            "openai_realtime",
            {
                "realtime_provider": "openai_realtime",
                "realtime_model": "gpt-realtime-2",
            },
        )


def test_runtime_accepts_exact_stack():
    validate_poc_runtime(
        "openai_realtime",
        {
            "realtime_provider": "openai_realtime",
            "realtime_model": "gpt-realtime-2.1-mini",
        },
    )


def test_default_engine_caps_are_conservative(monkeypatch):
    for name in (
        "POC_OPENAI_ENABLED",
        "POC_OPENAI_DAILY_LIMIT",
        "POC_GEMINI_ENABLED",
        "POC_GEMINI_DAILY_LIMIT",
        "POC_GOOGLE_CASCADE_ENABLED",
        "POC_GOOGLE_CASCADE_DAILY_LIMIT",
    ):
        monkeypatch.delenv(name, raising=False)
    assert engine_enabled("openai_realtime")
    assert engine_daily_limit("openai_realtime") == 20
    assert not engine_enabled("gemini_live")
    assert engine_daily_limit("gemini_live") == 0
    assert not engine_enabled("google_cascade")
    assert engine_daily_limit("google_cascade") == 0
