"""Idempotently seed the three AI receptionist POC workflows.

Usage:
  python -m api.services.poc.seed --organization-id 1 --user-id 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from api.db import db_client
from api.enums import ToolCategory
from api.services.workflow.dto import ReactFlowDTO

CANONICAL_PROMPT = """# ROLE
You are HTIS's inbound customer-support receptionist on a live phone call. Help the
caller check their own tickets, understand a ticket, create a new support ticket, or
reach Anurag Mehra.

# VOICE STYLE
- Reply in the caller's English, Hindi, or Hinglish and follow language switches.
- Sound warm and natural. Keep most turns to one or two short sentences.
- Ask one focused question at a time. Do not read long lists or use markdown aloud.
- If audio is unclear, ask casually for only the important detail to be repeated.
- Do not repeatedly use the caller's name; phone transcription may mishear it.

# IDENTITY AND PRIVACY
- Identify the caller only from the incoming caller ID by using get_caller.
- Never ask for or accept another person's mobile number to access tickets.
- Every lookup must remain scoped to the current caller. Never reveal cross-user data.
- A registered Employee maps to WFMS IssueType Internal. A registered Client maps to
  External. An unregistered caller also maps to External and has a blank EmployeeId.

# TOOL DISCIPLINE
- When invoking a tool, output only the tool call. Do not mix speech and a tool call.
- Never invent a profile, ticket, status, summary, or ticket number.
- Read at most three tickets initially. Give more only when the caller asks.
- Safe read failures may be retried once. Never blindly retry ticket creation after an
  ambiguous timeout or response.
- Ticket creation requires a fresh explicit yes or no confirmation after you read a
  concise final summary. A vague acknowledgement is not confirmation.

# NEW-TICKET CLASSIFICATION
Use only this POC taxonomy as run metadata:
- Employee: HR / Attendance and Leave; Finance / Salary and Payslip; Internal IT /
  WFMS Login, Portal or Email, VPN, or Credentials.
- Client: Network / Telecom / Network Outage or Slow or Degraded Service; IT
  Infrastructure / Hardware, LAN, or Wi-Fi; Software Support / WFMS ERP Issue.
- Anything else: Fallback / Other / Unknown.
Do not send these labels as undocumented WFMS request fields.

# SAFETY AND ESCALATION
- Collect only mandatory fields that are missing. For an unknown caller creating a
  ticket, collect name, email, and full address.
- Offer a human transfer when requested or when WFMS cannot safely complete the task.
- Transfer only after explicit consent. If transfer fails, apologize without promising
  a callback.
- Begin wrapping up around four minutes thirty seconds. The call ends at five minutes.
- Never claim a ticket exists unless WFMS returned its confirmed ticket number."""


STACKS = {
    "poc-openai": {
        "engine": "openai_realtime",
        "greeting": "You are connected to the OpenAI realtime support assistant. How may I help?",
        "model_overrides": {
            "is_realtime": True,
            "realtime": {
                "provider": "openai_realtime",
                "model": "gpt-realtime-2.1-mini",
                "language": "hi",
            },
        },
    },
    "poc-gemini-live": {
        "engine": "gemini_live",
        "greeting": "You are connected to the Gemini Live support assistant. How may I help?",
        "model_overrides": {
            "is_realtime": True,
            "realtime": {
                "provider": "google_realtime",
                "model": "gemini-3.1-flash-live-preview",
                "language": "hi",
            },
        },
    },
    "poc-google-cascade": {
        "engine": "google_cascade",
        "greeting": "You are connected to the Google cascade support assistant. How may I help?",
        "model_overrides": {
            "is_realtime": False,
            "stt": {
                "provider": "google",
                "model": "latest_short",
                "language": "hi-IN,en-IN",
            },
            "llm": {"provider": "google", "model": "gemini-3.8-flash"},
            "tts": {
                "provider": "google",
                "model": "wavenet",
                "voice": "hi-IN-Wavenet-A",
                "language": "hi-IN",
            },
        },
    },
}


NATIVE_FUNCTIONS = (
    "get_caller",
    "get_my_tickets",
    "get_ticket_details",
    "get_ticket_summary",
    "prepare_support_ticket",
    "create_support_ticket",
)


async def _sync_tools(organization_id: int, user_id: int) -> dict[str, str]:
    existing = {
        tool.name: tool
        for tool in await db_client.get_tools_for_organization(organization_id)
    }
    uuids: dict[str, str] = {}
    for function in NATIVE_FUNCTIONS:
        name = f"POC {function}"
        definition = {
            "schema_version": 1,
            "type": "native",
            "config": {"function": function, "timeout_ms": 8000},
        }
        tool = existing.get(name)
        if tool:
            tool = await db_client.update_tool(
                tool.tool_uuid, organization_id, definition=definition, status="active"
            )
        else:
            tool = await db_client.create_tool(
                organization_id,
                user_id,
                name,
                definition,
                category=ToolCategory.NATIVE.value,
                description=f"Caller-scoped POC operation: {function}",
                icon="headphones",
            )
        uuids[function] = tool.tool_uuid

    control_tools = [
        (
            "transfer_to_anurag",
            "POC Transfer to Anurag",
            ToolCategory.TRANSFER_CALL.value,
            {
                "schema_version": 1,
                "type": "transfer_call",
                "config": {
                    "destination_source": "static",
                    "destination": os.getenv(
                        "POC_ANURAG_SIP_DESTINATION", "PJSIP/anurag"
                    ),
                    "messageType": "custom",
                    "customMessage": "Please hold while I connect you with Anurag.",
                    "timeout": 30,
                },
            },
        ),
        (
            "end_call",
            "POC End Call",
            ToolCategory.END_CALL.value,
            {
                "schema_version": 1,
                "type": "end_call",
                "config": {
                    "messageType": "custom",
                    "customMessage": "Thank you for calling HTIS. Goodbye.",
                },
            },
        ),
    ]
    for key, name, category, definition in control_tools:
        tool = existing.get(name)
        if tool:
            tool = await db_client.update_tool(
                tool.tool_uuid, organization_id, definition=definition, status="active"
            )
        else:
            tool = await db_client.create_tool(
                organization_id,
                user_id,
                name,
                definition,
                category=category,
                icon="phone",
            )
        uuids[key] = tool.tool_uuid
    return uuids


def _workflow_json(tool_uuids: dict[str, str], greeting: str) -> dict:
    def tools(*names: str) -> list[str]:
        return [tool_uuids[name] for name in names]

    value: dict = {
        "nodes": [
            {
                "id": "start",
                "type": "startCall",
                "position": {"x": 300, "y": 0},
                "data": {
                    "name": "Welcome and identify caller",
                    "prompt": """The spoken greeting has already welcomed the caller.
Immediately call get_caller once to identify the incoming number. Do not ask the caller
for a phone number. Briefly acknowledge only profile details useful to the call, then
ask how you can help. Stay here for up to three caller turns if needed to understand
their intent. Move to Support triage once you know whether they want an existing
ticket, a new ticket, general guidance, or a human. Do not create or discuss a ticket
in detail in this opening stage.""",
                    "greeting_type": "text",
                    "greeting": greeting,
                    "allow_interrupt": True,
                    "add_global_prompt": True,
                    "is_start": True,
                    "tool_uuids": tools("get_caller"),
                },
            },
            {
                "id": "triage",
                "type": "agentNode",
                "position": {"x": 300, "y": 330},
                "data": {
                    "name": "Support triage",
                    "prompt": """Confirm your understanding of the caller's goal in one short
sentence. Answer simple general guidance when it is supported by the conversation, but
do not invent product facts. Route existing-ticket questions to Existing ticket help.
Route a new incident or service request to Create a support ticket. If the caller asks
for a person, or the request cannot be completed safely, obtain explicit permission and
route to Human escalation. If the caller is finished, route to Close call.""",
                    "allow_interrupt": True,
                    "add_global_prompt": True,
                },
            },
            {
                "id": "existing-ticket",
                "type": "agentNode",
                "position": {"x": -180, "y": 690},
                "data": {
                    "name": "Existing ticket help",
                    "prompt": """Help only with tickets belonging to the identified caller.
Call get_my_tickets when a list or status overview is needed and present no more than
three tickets first. Use get_ticket_details for exact fields and get_ticket_summary for
a concise explanation. Do not ask for another person's phone number. After answering,
ask whether the caller needs help with anything else. Route another request back to
Support triage, a new issue to Create a support ticket, an approved human request to
Human escalation, or a completed conversation to Close call.""",
                    "allow_interrupt": True,
                    "add_global_prompt": True,
                    "tool_uuids": tools(
                        "get_my_tickets", "get_ticket_details", "get_ticket_summary"
                    ),
                },
            },
            {
                "id": "new-ticket",
                "type": "agentNode",
                "position": {"x": 720, "y": 690},
                "data": {
                    "name": "Create a support ticket",
                    "prompt": """Understand the issue and collect only information required by
WFMS. For an unknown caller, collect missing name, email, and full address; leave
EmployeeId blank. Choose the closest allowed POC classification. Call
prepare_support_ticket before creation. Read its concise summary back, then ask a clear
yes or no confirmation question and wait. Call create_support_ticket only after an
explicit yes in the immediately following caller turn. If the answer changes any field,
prepare and confirm again. Never retry an ambiguous create result. After a confirmed
success, state the returned ticket number and ask whether anything else is needed.""",
                    "allow_interrupt": True,
                    "add_global_prompt": True,
                    "tool_uuids": tools(
                        "prepare_support_ticket", "create_support_ticket"
                    ),
                },
            },
            {
                "id": "human",
                "type": "agentNode",
                "position": {"x": 1160, "y": 1030},
                "data": {
                    "name": "Human escalation",
                    "prompt": """Enter this stage only after the caller explicitly agreed to a
human transfer. Tell them briefly that you are connecting them with Anurag, then invoke
the transfer tool as a separate tool-only turn. If it fails or is unavailable, apologize
briefly, do not promise a callback, and route to Close call.""",
                    "allow_interrupt": True,
                    "add_global_prompt": True,
                    "tool_uuids": tools("transfer_to_anurag"),
                },
            },
            {
                "id": "close",
                "type": "endCall",
                "position": {"x": 300, "y": 1320},
                "data": {
                    "name": "Close call",
                    "prompt": "Thank the caller briefly and end the call. Use no more than twelve words, ask no new question, and make no new promise.",
                    "add_global_prompt": False,
                    "is_end": True,
                },
            },
            {
                "id": "global",
                "type": "globalNode",
                "position": {"x": -620, "y": 400},
                "data": {
                    "name": "HTIS support policy",
                    "prompt": CANONICAL_PROMPT,
                    "allow_interrupt": True,
                },
            },
        ],
        "edges": [
            {
                "id": "start-triage",
                "type": "custom",
                "animated": True,
                "source": "start",
                "target": "triage",
                "data": {
                    "label": "Caller and intent understood",
                    "condition": "The caller has been identified from caller ID and their support goal is clear enough to route.",
                },
            },
            {
                "id": "start-human",
                "type": "custom",
                "animated": True,
                "source": "start",
                "target": "human",
                "data": {
                    "label": "Human requested",
                    "condition": "The caller explicitly asks for a person and agrees to be transferred to Anurag.",
                },
            },
            {
                "id": "start-close",
                "type": "custom",
                "animated": True,
                "source": "start",
                "target": "close",
                "data": {
                    "label": "Wrong number or stop",
                    "condition": "This is spam, a wrong number, or the caller clearly does not want to continue.",
                },
            },
            {
                "id": "triage-existing",
                "type": "custom",
                "animated": True,
                "source": "triage",
                "target": "existing-ticket",
                "data": {
                    "label": "Existing ticket",
                    "condition": "The caller wants a ticket list, status, details, or summary for one of their existing tickets.",
                },
            },
            {
                "id": "triage-new",
                "type": "custom",
                "animated": True,
                "source": "triage",
                "target": "new-ticket",
                "data": {
                    "label": "New support request",
                    "condition": "The caller wants to report a new issue or create a support ticket.",
                },
            },
            {
                "id": "triage-human",
                "type": "custom",
                "animated": True,
                "source": "triage",
                "target": "human",
                "data": {
                    "label": "Escalate to Anurag",
                    "condition": "The caller explicitly agrees to a human transfer, or WFMS cannot complete the task and the caller accepts escalation.",
                },
            },
            {
                "id": "triage-close",
                "type": "custom",
                "animated": True,
                "source": "triage",
                "target": "close",
                "data": {
                    "label": "No further help",
                    "condition": "The caller confirms they need nothing else.",
                },
            },
            {
                "id": "existing-new",
                "type": "custom",
                "animated": True,
                "source": "existing-ticket",
                "target": "new-ticket",
                "data": {
                    "label": "Create another ticket",
                    "condition": "The caller now wants to report a new issue.",
                },
            },
            {
                "id": "existing-triage",
                "type": "custom",
                "animated": True,
                "source": "existing-ticket",
                "target": "triage",
                "data": {
                    "label": "Another request",
                    "condition": "The existing-ticket question is handled and the caller has a different request.",
                },
            },
            {
                "id": "existing-human",
                "type": "custom",
                "animated": True,
                "source": "existing-ticket",
                "target": "human",
                "data": {
                    "label": "Human help",
                    "condition": "The caller explicitly agrees to transfer to Anurag.",
                },
            },
            {
                "id": "existing-close",
                "type": "custom",
                "animated": True,
                "source": "existing-ticket",
                "target": "close",
                "data": {
                    "label": "Resolved",
                    "condition": "The caller's ticket question is answered and they need nothing else.",
                },
            },
            {
                "id": "new-triage",
                "type": "custom",
                "animated": True,
                "source": "new-ticket",
                "target": "triage",
                "data": {
                    "label": "Another request",
                    "condition": "Ticket creation is complete or abandoned and the caller has another support request.",
                },
            },
            {
                "id": "new-human",
                "type": "custom",
                "animated": True,
                "source": "new-ticket",
                "target": "human",
                "data": {
                    "label": "Creation needs human",
                    "condition": "The caller explicitly agrees to transfer after ticket creation cannot safely complete or they request a person.",
                },
            },
            {
                "id": "new-close",
                "type": "custom",
                "animated": True,
                "source": "new-ticket",
                "target": "close",
                "data": {
                    "label": "Ticket handled",
                    "condition": "The ticket was created or deliberately not created, and the caller needs nothing else.",
                },
            },
            {
                "id": "human-close",
                "type": "custom",
                "animated": True,
                "source": "human",
                "target": "close",
                "data": {
                    "label": "Transfer finished",
                    "condition": "The transfer attempt failed or returned control to the AI and the call should now close.",
                },
            },
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 0.75},
    }
    # Validate the runtime contract, then keep React Flow presentation fields
    # such as custom edge type, animation, and viewport for the visual builder.
    ReactFlowDTO.model_validate(value)
    return value


async def seed(organization_id: int, user_id: int) -> dict[str, int]:
    tool_uuids = await _sync_tools(organization_id, user_id)
    existing = {
        item.name: item
        for item in await db_client.get_all_workflows_for_listing(organization_id)
    }
    ids: dict[str, int] = {}
    for name, stack in STACKS.items():
        definition = _workflow_json(tool_uuids, stack["greeting"])
        configurations = {
            "max_call_duration": 300,
            "max_user_idle_timeout": 30,
            "model_overrides": stack["model_overrides"],
        }
        workflow = existing.get(name)
        if workflow is None:
            workflow = await db_client.create_workflow(
                name, definition, user_id, organization_id
            )
        # Both create_workflow and the listing query return detached ORM
        # instances. Re-fetch with eager-loaded definitions before reading the
        # relationship, otherwise a fresh database fails on the first seed.
        workflow = await db_client.get_workflow(
            workflow.id, organization_id=organization_id
        )
        if workflow is None:
            raise RuntimeError(
                f"Workflow {name!r} disappeared while seeding organization "
                f"{organization_id}"
            )
        released = workflow.released_definition
        if (
            released
            and released.workflow_json == definition
            and (released.workflow_configurations or {}) == configurations
        ):
            ids[stack["engine"]] = workflow.id
            continue
        await db_client.save_workflow_draft(
            workflow.id,
            workflow_definition=definition,
            workflow_configurations=configurations,
        )
        await db_client.publish_workflow_draft(workflow.id)
        ids[stack["engine"]] = workflow.id
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-id", type=int, required=True)
    parser.add_argument("--user-id", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(seed(args.organization_id, args.user_id)), indent=2))


if __name__ == "__main__":
    main()
