from datetime import UTC, datetime
from types import SimpleNamespace

from api.services.poc.inspector import calls_csv, detail_run, summarize_run


def _run():
    return SimpleNamespace(
        id=41,
        created_at=datetime(2026, 9, 9, tzinfo=UTC),
        initial_context={
            "poc_engine": "google_cascade",
            "caller_number": "+91 98765 43210",
            "caller_e164": "+919876543210",
            "wfms_mobile": "9876543210",
            "asterisk_call_id": "asterisk-41",
            "runtime_configuration": {
                "stt_model": "chirp_3",
                "stt_language": "hi-IN,en-IN",
                "llm_model": "gemini-3.8-flash",
                "tts_model": "wavenet",
            },
        },
        gathered_context={
            "poc_outcome": "ticket_created",
            "ticket_number": "T-41",
            "poc_latency": {"time_to_first_response_ms": 315},
            "poc_cost": {
                "estimated_total": 0.02,
                "normalized_list_cost_usd": 0.02,
                "actual_billed_estimate_usd": 0.02,
            },
        },
        usage_info={"call_duration_seconds": 62},
        cost_info={},
        logs={},
        transcript_url="transcripts/41.txt",
        recording_url="recordings/41.wav",
    )


def test_summary_and_csv_expose_comparison_fields():
    run = _run()
    summary = summarize_run(run)
    assert summary.caller == "******3210"
    assert summary.models == "chirp_3 + gemini-3.8-flash + wavenet"
    assert summary.language == "hi-IN,en-IN"
    assert summary.first_response_latency_ms == 315
    csv_text = calls_csv([run])
    assert "normalized_list_cost_usd" in csv_text
    assert "gemini-3.8-flash" in csv_text


def test_detail_exposes_correlated_identifiers_to_authenticated_route():
    detail = detail_run(_run())
    assert detail.asterisk_call_id == "asterisk-41"
    assert detail.caller_number == "+91 98765 43210"
    assert detail.caller_e164 == "+919876543210"
    assert detail.wfms_mobile == "9876543210"
    assert detail.initial_context["caller_number"] == "******3210"
