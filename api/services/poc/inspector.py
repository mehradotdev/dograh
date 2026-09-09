from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from api.schemas.poc import PocCallDetail, PocCallSummary
from api.services.poc.config import SETTINGS
from api.services.poc.phone import masked_mobile


def engine_for_run(run: Any) -> str:
    return (run.gathered_context or {}).get("poc_engine") or (
        run.initial_context or {}
    ).get("poc_engine")


def runtime_for_run(run: Any) -> dict[str, Any]:
    return dict((run.initial_context or {}).get("runtime_configuration") or {})


def models_for_run(run: Any) -> str:
    runtime = runtime_for_run(run)
    models = [
        str(value) for key, value in runtime.items() if key.endswith("_model") and value
    ]
    return " + ".join(models) or "unknown"


def language_for_run(run: Any) -> str:
    initial = run.initial_context or {}
    gathered = run.gathered_context or {}
    runtime = runtime_for_run(run)
    return str(
        gathered.get("language")
        or initial.get("language")
        or runtime.get("realtime_language")
        or runtime.get("stt_language")
        or "English / Hindi / Hinglish"
    )


def recording_path_for_run(run: Any) -> Path | None:
    initial_context = (
        run.get("initial_context", {})
        if isinstance(run, dict)
        else run.initial_context or {}
    )
    call_id = str(initial_context.get("asterisk_call_id") or "")
    if not call_id or not all(ch.isalnum() or ch in ".-_" for ch in call_id):
        return None
    base = SETTINGS.recordings_dir.resolve()
    candidate = (base / f"{call_id}.wav").resolve()
    if candidate.parent != base:
        return None
    return candidate


def summarize_run(run: Any) -> PocCallSummary:
    initial = run.initial_context or {}
    gathered = run.gathered_context or {}
    usage = run.usage_info or {}
    cost = gathered.get("poc_cost") or (run.cost_info or {}).get("poc") or {}
    latency = gathered.get("poc_latency") or {}
    return PocCallSummary(
        id=run.id,
        created_at=run.created_at,
        engine=engine_for_run(run),
        models=models_for_run(run),
        language=language_for_run(run),
        caller=masked_mobile(
            initial.get("caller_number") or initial.get("phone_number")
        ),
        duration_seconds=int(usage.get("call_duration_seconds") or 0),
        outcome=gathered.get("poc_outcome")
        or gathered.get("call_disposition")
        or "unknown",
        ticket_number=gathered.get("ticket_number"),
        estimated_cost_usd=cost.get("estimated_total"),
        normalized_list_cost_usd=cost.get("normalized_list_cost_usd"),
        actual_billed_estimate_usd=cost.get("actual_billed_estimate_usd"),
        first_response_latency_ms=latency.get("time_to_first_response_ms"),
    )


def detail_run(run: Any) -> PocCallDetail:
    initial_context = dict(run.initial_context or {})
    for key in ("caller_number", "phone_number"):
        if key in initial_context:
            initial_context[key] = masked_mobile(str(initial_context[key]))
    return PocCallDetail(
        **summarize_run(run).model_dump(),
        asterisk_call_id=initial_context.get("asterisk_call_id"),
        caller_number=(run.initial_context or {}).get("caller_number"),
        caller_e164=(run.initial_context or {}).get("caller_e164"),
        wfms_mobile=(run.initial_context or {}).get("wfms_mobile"),
        runtime_configuration=runtime_for_run(run),
        initial_context=initial_context,
        gathered_context=run.gathered_context or {},
        usage_info=run.usage_info or {},
        cost_info=run.cost_info or {},
        logs=run.logs or {},
        transcript_url=run.transcript_url,
        dograh_recording_url=run.recording_url,
        recording_available=bool(
            recording_path_for_run(run) and recording_path_for_run(run).is_file()
        ),
    )


def calls_csv(rows: list[Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "run_id",
            "started_at",
            "engine",
            "models",
            "language",
            "caller",
            "duration_seconds",
            "outcome",
            "ticket_number",
            "estimated_cost_usd",
            "normalized_list_cost_usd",
            "actual_billed_estimate_usd",
            "first_response_latency_ms",
        ],
    )
    writer.writeheader()
    for row in rows:
        item = summarize_run(row)
        writer.writerow(
            {
                "run_id": item.id,
                "started_at": item.created_at.isoformat(),
                "engine": item.engine,
                "models": item.models,
                "language": item.language,
                "caller": item.caller,
                "duration_seconds": item.duration_seconds,
                "outcome": item.outcome,
                "ticket_number": item.ticket_number or "",
                "estimated_cost_usd": item.estimated_cost_usd
                if item.estimated_cost_usd is not None
                else "",
                "normalized_list_cost_usd": item.normalized_list_cost_usd
                if item.normalized_list_cost_usd is not None
                else "",
                "actual_billed_estimate_usd": item.actual_billed_estimate_usd
                if item.actual_billed_estimate_usd is not None
                else "",
                "first_response_latency_ms": item.first_response_latency_ms
                if item.first_response_latency_ms is not None
                else "",
            }
        )
    return output.getvalue()
