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

CANONICAL_PROMPT = """You are HTIS's inbound support receptionist on a voice call.
Speak naturally in the caller's English, Hindi, or Hinglish. Keep answers brief and
never read more than three tickets at first. Use only the caller-scoped WFMS tools.
Never ask for or accept another person's mobile number for ticket access.

First identify the caller with get_caller. Employee maps to IssueType Internal;
Client maps to External. An unregistered caller also maps to External; collect their
name, email address, and full address, and leave EmployeeId blank. Classify support
requests only with this POC taxonomy:
Employee: HR / Attendance & Leave; Finance / Salary & Payslip; Internal IT /
WFMS Login / Portal or Email / VPN / Credentials. Client: Network / Telecom /
Network Outage or Slow / Degraded Service; IT Infrastructure / Hardware / LAN /
Wi-Fi; Software Support / WFMS ERP Issue. Otherwise use Fallback / Other / Unknown.
These labels are run metadata, not undocumented WFMS fields.

Before ticket creation, collect only fields missing from the caller profile, call
prepare_support_ticket, read back a concise summary, and ask an explicit yes/no
question. Call create_support_ticket only after a new explicit caller confirmation.
Never retry an ambiguous creation result. Offer transfer to Anurag if WFMS fails or
the caller asks for a person. Ask before using the transfer tool. If transfer fails,
apologize and end the call.

At about four minutes thirty seconds, wrap up naturally. The call ends at five
minutes. Do not offer a callback queue. Never claim a ticket exists without the
confirmed ticket number returned by WFMS."""


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


async def _sync_tools(organization_id: int, user_id: int) -> list[str]:
    existing = {
        tool.name: tool
        for tool in await db_client.get_tools_for_organization(organization_id)
    }
    uuids: list[str] = []
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
        uuids.append(tool.tool_uuid)

    control_tools = [
        (
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
    for name, category, definition in control_tools:
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
        uuids.append(tool.tool_uuid)
    return uuids


def _workflow_json(tool_uuids: list[str], greeting: str) -> dict:
    value = {
        "nodes": [
            {
                "id": "start",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {
                    "name": "AI receptionist",
                    "prompt": "Assist the inbound caller according to the global POC policy.",
                    "greeting_type": "text",
                    "greeting": greeting,
                    "allow_interrupt": True,
                    "add_global_prompt": True,
                    "tool_uuids": tool_uuids,
                },
            },
            {
                "id": "global",
                "type": "globalNode",
                "position": {"x": 0, "y": -240},
                "data": {"name": "Canonical POC policy", "prompt": CANONICAL_PROMPT},
            },
        ],
        "edges": [],
    }
    return ReactFlowDTO.model_validate(value).model_dump(mode="json")


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
