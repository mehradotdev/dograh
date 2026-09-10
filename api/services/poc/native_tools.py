from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

from api.services.poc.wfms import WfmsClient, WfmsError
from api.services.poc.wfms_models import TicketDraft

NATIVE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_caller": {
        "description": "Look up the current caller in WFMS.",
        "properties": {},
        "required": [],
    },
    "get_my_tickets": {
        "description": "List tickets belonging to the current caller.",
        "properties": {},
        "required": [],
    },
    "get_ticket_details": {
        "description": "Get one of the current caller's tickets.",
        "properties": {"ticket_number": {"type": "string"}},
        "required": ["ticket_number"],
    },
    "get_ticket_summary": {
        "description": "Get the status history for one of the current caller's tickets.",
        "properties": {"ticket_number": {"type": "string"}},
        "required": ["ticket_number"],
    },
    "prepare_support_ticket": {
        "description": "Validate and summarize a support-ticket draft. Read it back and ask the caller to confirm before calling create_support_ticket.",
        "properties": {
            "query_title": {"type": "string"},
            "description": {"type": "string"},
            "issue_type": {"type": "string", "enum": ["Internal", "External"]},
            "user_name": {"type": "string"},
            "email": {"type": "string"},
            "employee_id": {"type": "string"},
            "full_address": {"type": "string"},
            "caller_type": {
                "type": "string",
                "enum": ["Employee", "Client", "Unknown"],
            },
            "category": {"type": "string"},
            "subcategory": {"type": "string"},
        },
        "required": [
            "query_title",
            "description",
            "issue_type",
            "caller_type",
            "category",
            "subcategory",
        ],
    },
    "create_support_ticket": {
        "description": "Create the prepared ticket only after a new, explicit caller confirmation.",
        "properties": {"confirmation_token": {"type": "string"}},
        "required": ["confirmation_token"],
    },
}


def get_native_tool_schema(function: str) -> dict[str, Any]:
    try:
        return NATIVE_TOOL_SCHEMAS[function]
    except KeyError as exc:
        raise ValueError(f"Unsupported native tool function: {function}") from exc


_YES = re.compile(
    r"\b(yes|confirm|confirmed|go ahead|create it|please create|haan|ha+|hanji|ji haan|kar do|bana do|theek hai)\b",
    re.IGNORECASE,
)
_NO = re.compile(r"\b(no|don't|do not|cancel|nahi|mat karo)\b", re.IGNORECASE)


def is_explicit_confirmation(text: str) -> bool:
    return bool(_YES.search(text)) and not bool(_NO.search(text))


def _message_text(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )
    return str(getattr(message, "content", "") or "")


def _user_messages(engine: Any) -> list[Any]:
    messages = getattr(getattr(engine, "context", None), "messages", []) or []
    return [
        m
        for m in messages
        if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None))
        == "user"
    ]


def _transcription_snapshot(engine: Any) -> tuple[int, str]:
    snapshot = getattr(engine, "user_transcription_snapshot", None)
    if not callable(snapshot):
        return 0, ""
    revision, text = snapshot()
    return int(revision), str(text or "")


@dataclass
class PendingTicket:
    token: str
    draft: TicketDraft
    user_turn_count: int
    transcription_revision: int


class PocToolSession:
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        context = getattr(engine, "_call_context_vars", {}) or {}
        self.client = WfmsClient(
            context.get("caller_number") or context.get("phone_number")
        )
        self.pending: PendingTicket | None = None

    async def aclose(self) -> None:
        await self.client.aclose()

    async def execute(self, function: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        outcome = "success"
        try:
            if function == "get_caller":
                profile = await self.client.get_caller()
                result = {
                    "registered": profile is not None,
                    "caller": profile.model_dump() if profile else None,
                }
            elif function == "get_my_tickets":
                result = {
                    "tickets": [
                        t.model_dump() for t in await self.client.get_my_tickets()
                    ]
                }
            elif function == "get_ticket_details":
                result = (
                    await self.client.get_ticket_details(arguments["ticket_number"])
                ).model_dump()
            elif function == "get_ticket_summary":
                result = {
                    "history": [
                        r.model_dump()
                        for r in await self.client.get_ticket_summary(
                            arguments["ticket_number"]
                        )
                    ]
                }
            elif function == "prepare_support_ticket":
                draft = TicketDraft.model_validate(arguments)
                token = secrets.token_urlsafe(18)
                transcription_revision, _ = _transcription_snapshot(self.engine)
                self.pending = PendingTicket(
                    token,
                    draft,
                    len(_user_messages(self.engine)),
                    transcription_revision,
                )
                result = {
                    "confirmation_token": token,
                    "draft": draft.model_dump(),
                    "instruction": "Read this draft back and obtain a new explicit confirmation.",
                }
            elif function == "create_support_ticket":
                result = await self._create(arguments.get("confirmation_token", ""))
            else:
                raise ValueError(f"Unsupported native function: {function}")
        except (WfmsError, ValueError, KeyError) as exc:
            outcome = "error"
            result = {"error": str(exc)}
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        gathered = self.engine._gathered_context
        events = gathered.setdefault("poc_tool_events", [])
        event = {"function": function, "outcome": outcome, "latency_ms": elapsed_ms}
        if self.client.last_exchange:
            event["wfms"] = dict(self.client.last_exchange)
        events.append(event)
        return result

    async def _create(self, token: str) -> dict[str, Any]:
        pending = self.pending
        if not pending or not secrets.compare_digest(token, pending.token):
            raise ValueError("No matching prepared ticket; prepare the draft again")
        turns = _user_messages(self.engine)
        confirmation_text = ""
        has_fresh_confirmation = len(turns) > pending.user_turn_count
        if has_fresh_confirmation:
            confirmation_text = _message_text(turns[-1])

        transcription_revision, transcription_text = _transcription_snapshot(
            self.engine
        )
        if transcription_revision > pending.transcription_revision:
            has_fresh_confirmation = True
            confirmation_text = transcription_text

        if not has_fresh_confirmation or not is_explicit_confirmation(
            confirmation_text
        ):
            raise ValueError(
                "The caller has not explicitly confirmed this prepared ticket"
            )
        profile = await self.client.get_caller()
        result = await self.client.create_ticket(pending.draft, profile=profile)
        self.pending = None
        self.engine._gathered_context.update(
            {
                "ticket_number": result.ticket_number,
                "poc_outcome": "ticket_created",
                "caller_type": pending.draft.caller_type,
                "category": pending.draft.category,
                "subcategory": pending.draft.subcategory,
            }
        )
        return result.model_dump(by_alias=True)
