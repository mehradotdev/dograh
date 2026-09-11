from __future__ import annotations

import asyncio
import itertools
import time
from typing import Any

import httpx

from api.services.poc.config import SETTINGS, PocSettings
from api.services.poc.phone import normalize_indian_mobile
from api.services.poc.wfms_models import (
    CallerProfile,
    CreateTicketResult,
    Ticket,
    TicketDraft,
    TicketSummaryRow,
)


class WfmsError(RuntimeError):
    pass


class WfmsNotFound(WfmsError):
    pass


class WfmsPrivacyError(WfmsError):
    pass


class WfmsAmbiguousCreate(WfmsError):
    pass


class WfmsClient:
    """Narrow caller-scoped WFMS adapter; no arbitrary mobile-number access."""

    def __init__(
        self,
        caller_number: str,
        *,
        settings: PocSettings = SETTINGS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.mobile = normalize_indian_mobile(caller_number)
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.wfms_base_url.rstrip("/"),
            timeout=settings.wfms_timeout_seconds,
            transport=transport,
        )
        self.last_exchange: dict[str, Any] | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        for attempt in range(2):
            started = time.perf_counter()
            try:
                response = await self._client.get(path, params=params)
                self.last_exchange = {
                    "method": "GET",
                    "path": path,
                    "status": response.status_code,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                }
                if response.status_code >= 500 and attempt == 0:
                    await asyncio.sleep(0)
                    continue
                return response
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt:
                    raise WfmsError("WFMS is temporarily unavailable")
                await asyncio.sleep(0)
        raise WfmsError("WFMS is temporarily unavailable")

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise WfmsError("WFMS returned an invalid response") from exc

    async def get_caller(self) -> CallerProfile | None:
        if self.settings.wfms_mode == "mock":
            return CallerProfile.model_validate(
                {
                    "UserType": "Employee",
                    "Id": 1001,
                    "Code": "1001",
                    "Name": "Mock Caller",
                    "MobileNo": self.mobile,
                    "Email": "mock.caller@example.invalid",
                }
            )
        response = await self._get(
            "/api/whatsapp/get-user-details",
            {"mobileNo": self.mobile},
        )
        body = self._json(response)
        if not isinstance(body, dict):
            raise WfmsError("WFMS returned an invalid caller response")
        if response.status_code != 200 or not body.get("success"):
            raise WfmsError(body.get("message") or "Unable to look up caller")
        data = body.get("data") or {}
        if data.get("UserType") == "NotFound":
            return None
        profile = CallerProfile.model_validate(data)
        if profile.mobile and normalize_indian_mobile(profile.mobile) != self.mobile:
            raise WfmsPrivacyError("WFMS returned a different caller")
        return profile

    async def get_my_tickets(
        self, *, page: int = 1, page_size: int = 10
    ) -> list[Ticket]:
        if self.settings.wfms_mode == "mock":
            return []
        response = await self._get(
            "/api/whatsapp/get-registered-tickets",
            {"mobileNo": self.mobile, "page": page, "pageSize": min(page_size, 25)},
        )
        body = self._json(response)
        if response.status_code == 404:
            return []
        if not isinstance(body, dict):
            raise WfmsError("WFMS returned an invalid ticket-list response")
        if response.status_code != 200 or not body.get("success"):
            raise WfmsError(body.get("message") or "Unable to fetch tickets")
        tickets = [Ticket.model_validate(item) for item in body.get("data", [])]
        for ticket in tickets:
            self._assert_ownership(ticket)
        return tickets

    def _assert_ownership(self, ticket: Ticket) -> None:
        try:
            owned = normalize_indian_mobile(ticket.contact_number)
        except ValueError as exc:
            raise WfmsPrivacyError("Ticket has no verifiable owner") from exc
        if owned != self.mobile:
            raise WfmsPrivacyError("Ticket does not belong to this caller")

    async def get_ticket_details(self, ticket_number: str) -> Ticket:
        if self.settings.wfms_mode == "mock":
            raise WfmsNotFound("Ticket not found in mock WFMS")
        response = await self._get(
            "/api/whatsapp/get-ticket-details",
            {"ticketNumber": ticket_number.strip()},
        )
        body = self._json(response)
        if response.status_code == 404:
            raise WfmsNotFound("Ticket not found")
        if response.status_code != 200 or not isinstance(body, dict):
            raise WfmsError("Unable to fetch ticket details")
        ticket = Ticket.model_validate(body)
        self._assert_ownership(ticket)
        return ticket

    async def get_ticket_summary(self, ticket_number: str) -> list[TicketSummaryRow]:
        # The discovered endpoint can return ticket 19 for a bogus ticket number.
        # Details is therefore the ownership and identity authority.
        ticket = await self.get_ticket_details(ticket_number)
        response = await self._get(
            "/api/whatsapp/get-ticket-detail-summary",
            {"ticketNumber": ticket.ticket_number},
        )
        body = self._json(response)
        if response.status_code != 200 or not isinstance(body, list):
            raise WfmsError("Unable to fetch ticket summary")
        rows = [TicketSummaryRow.model_validate(row) for row in body]
        matching_rows = [row for row in rows if row.ticket_id == ticket.request_id]
        discarded_rows = len(rows) - len(matching_rows)
        if discarded_rows and self.last_exchange is not None:
            # WFMS is known to return another ticket's history for some valid
            # ticket numbers. Discard those rows instead of exposing them or
            # turning an otherwise valid caller-scoped lookup into a hard
            # failure. An empty history tells the agent that WFMS did not
            # provide the requested timeline without leaking cross-ticket data.
            self.last_exchange["discarded_mismatched_rows"] = discarded_rows
        return matching_rows

    async def create_ticket(
        self, draft: TicketDraft, *, profile: CallerProfile | None
    ) -> CreateTicketResult:
        if profile is None and not self.settings.allow_unknown_caller_create:
            raise WfmsError(
                "Ticket creation for an unregistered caller is disabled until its "
                "WFMS contract is verified; transfer to Anurag instead."
            )
        if profile is None:
            required = {
                "name": draft.user_name,
                "email": draft.email,
                "full address": draft.full_address,
            }
            missing = [
                name for name, value in required.items() if not (value or "").strip()
            ]
            if missing:
                raise WfmsError(
                    "An unregistered caller must provide " + ", ".join(missing)
                )
            if draft.issue_type != "External":
                raise WfmsError("An unregistered caller must use IssueType External")
        payload = {
            "IssueType": draft.issue_type,
            "QueryTitle": draft.query_title,
            "Description": draft.description,
            "UserName": draft.user_name or (profile.name if profile else None),
            "Email": draft.email or (profile.email if profile else None),
            "ContactNumber": self.mobile,
            "EmployeeId": draft.employee_id or (profile.code if profile else ""),
            "FullAddress": draft.full_address,
            **draft.extra,
        }
        if self.settings.wfms_mode == "mock":
            return CreateTicketResult(
                success=True,
                message="Mock ticket created",
                ticketNumber=f"MOCK-{next(_MOCK_TICKET_IDS)}",
            )
        # Deliberately one attempt: retrying a POST could create duplicate tickets.
        started = time.perf_counter()
        try:
            response = await self._client.post(
                "/api/whatsapp/CreateTicket", json=payload
            )
            self.last_exchange = {
                "method": "POST",
                "path": "/api/whatsapp/CreateTicket",
                "status": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise WfmsAmbiguousCreate(
                "WFMS did not confirm creation. Do not retry; check tickets or transfer."
            ) from exc
        body = self._json(response)
        try:
            result = CreateTicketResult.model_validate(body)
        except (TypeError, ValueError) as exc:
            raise WfmsAmbiguousCreate(
                "WFMS returned an unrecognized creation response; do not retry"
            ) from exc
        if response.status_code == 200 and result.success and result.ticket_number:
            return result
        raise WfmsAmbiguousCreate(
            result.message or "WFMS did not provide an unambiguous ticket number"
        )


_MOCK_TICKET_IDS = itertools.count(1)
