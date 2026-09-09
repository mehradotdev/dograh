from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PRICING = json.loads((Path(__file__).with_name("pricing.json")).read_text())


def _tokens(usage: dict[str, Any], *names: str) -> int:
    return sum(int(usage.get(name) or 0) for name in names)


def calculate_poc_cost(engine: str, usage_info: dict[str, Any]) -> dict[str, Any]:
    """Calculate transparent estimated provider cost from persisted usage."""
    total = 0.0
    components: list[dict[str, Any]] = []

    def add(
        name: str,
        quantity: float,
        unit: str,
        rate: float,
        quantity_source: str,
    ) -> None:
        nonlocal total
        cost = quantity * rate
        total += cost
        components.append(
            {
                "name": name,
                "quantity": round(quantity, 6),
                "unit": unit,
                "rate_usd": rate,
                "cost_usd": round(cost, 6),
                "quantity_source": quantity_source,
            }
        )

    llm_entries = usage_info.get("llm", {}) or {}
    stt_entries = usage_info.get("stt", {}) or {}
    tts_entries = usage_info.get("tts", {}) or {}
    duration_minutes = float(usage_info.get("call_duration_seconds") or 0) / 60

    priced_gemini_live = False
    for key, usage in llm_entries.items():
        model = key.rsplit("|||", 1)[-1]
        rates = PRICING["models"].get(model, {})
        if model == "gemini-3.1-flash-live-preview":
            # Live API exposes token usage inconsistently across transports; the
            # documented per-minute equivalents are stable and auditable.
            if priced_gemini_live:
                continue
            priced_gemini_live = True
            add(
                "Gemini Live audio input",
                duration_minutes,
                "minute",
                rates["audio_input_per_minute"],
                "measured_call_duration_estimate",
            )
            add(
                "Gemini Live audio output",
                duration_minutes,
                "minute",
                rates["audio_output_per_minute"],
                "measured_call_duration_estimate",
            )
            continue
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        audio_in = _tokens(usage, "input_audio_tokens")
        audio_out = _tokens(usage, "output_audio_tokens")
        text_input_tokens = max(input_tokens - audio_in, 0)
        text_output_tokens = max(output_tokens - audio_out, 0)
        if rates.get("text_input_per_million"):
            add(
                f"{model} text input",
                text_input_tokens / 1_000_000,
                "million tokens",
                rates["text_input_per_million"],
                "provider_reported_usage",
            )
            add(
                f"{model} text output",
                text_output_tokens / 1_000_000,
                "million tokens",
                rates["text_output_per_million"],
                "provider_reported_usage",
            )
        if rates.get("audio_input_per_million"):
            add(
                f"{model} audio input",
                audio_in / 1_000_000,
                "million tokens",
                rates["audio_input_per_million"],
                "provider_reported_usage",
            )
            add(
                f"{model} audio output",
                audio_out / 1_000_000,
                "million tokens",
                rates["audio_output_per_million"],
                "provider_reported_usage",
            )

    if engine == "google_cascade":
        stt_seconds = sum(float(v or 0) for v in stt_entries.values())
        characters = sum(int(v or 0) for v in tts_entries.values())
        add(
            "Google STT V2 standard",
            stt_seconds / 60,
            "minute",
            0.016,
            "measured_audio_usage",
        )
        add(
            "Google WaveNet TTS",
            characters / 1_000_000,
            "million characters",
            4.0,
            "measured_character_usage",
        )

    estimated_total = round(total, 6)
    return {
        "currency": "USD",
        "estimated_total": estimated_total,
        "normalized_list_cost_usd": estimated_total,
        "actual_billed_estimate_usd": estimated_total,
        "actual_estimate_basis": "list price; invoice and free-tier adjustments unavailable",
        "components": components,
        "pricing_as_of": PRICING["as_of"],
        "pricing_version": PRICING["as_of"],
        "pricing_sources": PRICING["sources"],
    }


def summarize_latency(logs: Any, tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    first_response_values: list[float] = []
    turn_response_values: list[float] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, (int, float)) and key in {
                    "latency_ms",
                    "ttfb_ms",
                    "latency_measured",
                    "latency_seconds",
                    "ttfb_seconds",
                }:
                    milliseconds = (
                        float(child) * 1000
                        if key.endswith("_seconds")
                        else float(child)
                    )
                    values.append(milliseconds)
                    if key in {"ttfb_ms", "ttfb_seconds"}:
                        first_response_values.append(milliseconds)
                    else:
                        turn_response_values.append(milliseconds)
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(logs)
    tool_values = [
        float(event["latency_ms"])
        for event in tool_events
        if isinstance(event.get("latency_ms"), (int, float))
    ]
    return {
        "sample_count": len(values),
        "average_ms": round(sum(values) / len(values), 1) if values else None,
        "maximum_ms": round(max(values), 1) if values else None,
        "time_to_first_response_ms": (
            round(first_response_values[0], 1) if first_response_values else None
        ),
        "turn_response_ms": turn_response_values,
        "wfms_api_ms": [
            float(event["wfms"]["latency_ms"])
            for event in tool_events
            if isinstance(event.get("wfms"), dict)
            and isinstance(event["wfms"].get("latency_ms"), (int, float))
        ],
        "tool_average_ms": round(sum(tool_values) / len(tool_values), 1)
        if tool_values
        else None,
    }
