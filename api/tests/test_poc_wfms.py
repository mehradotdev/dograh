import httpx
import pytest

from api.services.poc.config import PocSettings
from api.services.poc.wfms import (
    WfmsAmbiguousCreate,
    WfmsClient,
    WfmsError,
)
from api.services.poc.wfms_models import CallerProfile, TicketDraft


def settings(**overrides):
    return PocSettings(wfms_base_url="https://wfms.test", wfms_mode="live", **overrides)


@pytest.mark.asyncio
async def test_caller_and_tickets_are_scoped_to_inbound_number():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        if request.url.path.endswith("/get-user-details"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {"UserType": "Employee", "Id": 1, "MobileNo": "9876543210"},
                },
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {
                        "RequestId": 19,
                        "TicketNumber": "HTIS-wfms-19",
                        "ContactNumber": "9876543210",
                    }
                ],
            },
        )

    client = WfmsClient(
        "+919876543210", settings=settings(), transport=httpx.MockTransport(handler)
    )
    assert (await client.get_caller()).id == 1
    assert len(await client.get_my_tickets()) == 1
    assert all(item["mobileNo"] == "9876543210" for item in seen)
    await client.aclose()


@pytest.mark.asyncio
async def test_summary_discards_wfms_wrong_ticket_bug():
    def handler(request):
        if request.url.path.endswith("/get-ticket-details"):
            return httpx.Response(
                200,
                json={
                    "RequestId": 22,
                    "TicketNumber": "HTIS-wfms-22",
                    "ContactNumber": "9876543210",
                },
            )
        return httpx.Response(
            200, json=[{"StatusId": 1, "TicketId": 19, "Status": "Open"}]
        )

    client = WfmsClient(
        "9876543210", settings=settings(), transport=httpx.MockTransport(handler)
    )
    assert await client.get_ticket_summary("HTIS-wfms-22") == []
    assert client.last_exchange["discarded_mismatched_rows"] == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_create_ticket_timeout_is_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("unknown result", request=request)

    client = WfmsClient(
        "9876543210", settings=settings(), transport=httpx.MockTransport(handler)
    )
    profile = CallerProfile.model_validate(
        {"UserType": "Employee", "Id": 1, "MobileNo": "9876543210"}
    )
    draft = TicketDraft(
        query_title="Login issue", description="Cannot sign in", issue_type="Internal"
    )
    with pytest.raises(WfmsAmbiguousCreate):
        await client.create_ticket(draft, profile=profile)
    assert calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_unknown_external_caller_can_create_with_required_fields():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "message": "Ticket generated successfully.",
                "ticketNumber": "A0030",
            },
        )

    client = WfmsClient(
        "9876543210",
        settings=settings(allow_unknown_caller_create=True),
        transport=httpx.MockTransport(handler),
    )
    draft = TicketDraft(
        query_title="Login issue",
        description="Cannot sign in",
        issue_type="External",
        user_name="External caller",
        email="external@example.invalid",
        employee_id="",
        full_address="Example address",
        caller_type="Unknown",
    )
    result = await client.create_ticket(draft, profile=None)
    assert result.ticket_number == "A0030"
    assert len(requests) == 1
    assert requests[0].url.path == "/api/whatsapp/CreateTicket"
    assert b'"EmployeeId":""' in requests[0].content
    await client.aclose()


@pytest.mark.asyncio
async def test_unknown_caller_requires_profile_fields_before_post():
    client = WfmsClient(
        "9876543210",
        settings=settings(allow_unknown_caller_create=True),
        transport=httpx.MockTransport(lambda _: pytest.fail("POST must not run")),
    )
    draft = TicketDraft(
        query_title="Login issue",
        description="Cannot sign in",
        issue_type="External",
        caller_type="Unknown",
    )
    with pytest.raises(WfmsError, match="name, email, full address"):
        await client.create_ticket(draft, profile=None)
    await client.aclose()
