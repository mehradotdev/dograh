from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.poc.native_tools import PocToolSession, is_explicit_confirmation


@pytest.mark.parametrize(
    "text", ["Yes, create it", "Haan ji", "ticket bana do", "Please create it"]
)
def test_accepts_explicit_hinglish_confirmation(text):
    assert is_explicit_confirmation(text)


@pytest.mark.parametrize(
    "text", ["maybe", "I see", "No, don't create it", "the details look right"]
)
def test_rejects_ambiguous_or_negative_confirmation(text):
    assert not is_explicit_confirmation(text)


@pytest.mark.asyncio
async def test_create_requires_new_user_turn(monkeypatch):
    engine = SimpleNamespace(
        _call_context_vars={"caller_number": "9876543210"},
        _gathered_context={},
        context=SimpleNamespace(
            messages=[{"role": "user", "content": "I cannot log in"}]
        ),
    )
    session = PocToolSession(engine)
    session.client.get_caller = AsyncMock(return_value=None)
    prepared = await session.execute(
        "prepare_support_ticket",
        {
            "query_title": "WFMS login failure",
            "description": "Usual password rejected",
            "issue_type": "Internal",
            "caller_type": "Employee",
            "category": "Internal IT",
            "subcategory": "WFMS Login / Portal",
        },
    )
    denied = await session.execute(
        "create_support_ticket", {"confirmation_token": prepared["confirmation_token"]}
    )
    assert "explicitly confirmed" in denied["error"]
    engine.context.messages.append({"role": "user", "content": "Yes, please create it"})
    session.client.create_ticket = AsyncMock(
        return_value=SimpleNamespace(
            ticket_number="MOCK-1",
            model_dump=lambda **_: {"success": True, "ticketNumber": "MOCK-1"},
        )
    )
    created = await session.execute(
        "create_support_ticket", {"confirmation_token": prepared["confirmation_token"]}
    )
    assert created["ticketNumber"] == "MOCK-1"
    assert engine._gathered_context["subcategory"] == "WFMS Login / Portal"
    await session.client.aclose()


@pytest.mark.asyncio
async def test_create_accepts_new_finalized_realtime_transcription():
    engine = SimpleNamespace(
        _call_context_vars={"caller_number": "9876543210"},
        _gathered_context={},
        context=SimpleNamespace(messages=[]),
        transcription_revision=1,
        latest_transcription="I cannot log in",
    )
    engine.user_transcription_snapshot = lambda: (
        engine.transcription_revision,
        engine.latest_transcription,
    )
    session = PocToolSession(engine)
    session.client.get_caller = AsyncMock(return_value=None)
    prepared = await session.execute(
        "prepare_support_ticket",
        {
            "query_title": "WFMS login failure",
            "description": "Usual password rejected",
            "issue_type": "External",
            "caller_type": "Unknown",
            "category": "Fallback",
            "subcategory": "Other",
        },
    )

    engine.transcription_revision += 1
    engine.latest_transcription = "Yes, create the ticket"
    session.client.create_ticket = AsyncMock(
        return_value=SimpleNamespace(
            ticket_number="MOCK-2",
            model_dump=lambda **_: {"success": True, "ticketNumber": "MOCK-2"},
        )
    )

    created = await session.execute(
        "create_support_ticket", {"confirmation_token": prepared["confirmation_token"]}
    )

    assert created["ticketNumber"] == "MOCK-2"
    await session.client.aclose()
