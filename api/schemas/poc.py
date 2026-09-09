from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PocCallSummary(BaseModel):
    id: int
    created_at: datetime
    engine: str
    models: str
    language: str
    caller: str
    duration_seconds: int
    outcome: str
    ticket_number: str | None = None
    estimated_cost_usd: float | None = None
    normalized_list_cost_usd: float | None = None
    actual_billed_estimate_usd: float | None = None
    first_response_latency_ms: float | None = None


class PocCallList(BaseModel):
    items: list[PocCallSummary]
    total: int


class PocCallDetail(PocCallSummary):
    asterisk_call_id: str | None = None
    caller_number: str | None = None
    caller_e164: str | None = None
    wfms_mobile: str | None = None
    runtime_configuration: dict[str, Any]
    initial_context: dict[str, Any]
    gathered_context: dict[str, Any]
    usage_info: dict[str, Any]
    cost_info: dict[str, Any]
    logs: Any
    transcript_url: str | None = None
    dograh_recording_url: str | None = None
    recording_available: bool


class DeletePocCallsRequest(BaseModel):
    run_ids: list[int] = Field(min_length=1, max_length=500)


class DeletePocCallsResponse(BaseModel):
    deleted: int
