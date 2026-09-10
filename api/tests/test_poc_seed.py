from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.poc import seed as poc_seed
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph


@pytest.mark.asyncio
async def test_seed_refetches_new_workflows_before_reading_definitions(monkeypatch):
    tool_uuids = {
        "get_caller": "tool-get-caller",
        "get_my_tickets": "tool-get-my-tickets",
        "get_ticket_details": "tool-get-ticket-details",
        "get_ticket_summary": "tool-get-ticket-summary",
        "prepare_support_ticket": "tool-prepare-ticket",
        "create_support_ticket": "tool-create-ticket",
        "transfer_to_anurag": "tool-transfer",
        "end_call": "tool-end-call",
    }
    monkeypatch.setattr(poc_seed, "_sync_tools", AsyncMock(return_value=tool_uuids))
    monkeypatch.setattr(
        poc_seed.db_client,
        "get_all_workflows_for_listing",
        AsyncMock(return_value=[]),
    )

    created = [SimpleNamespace(id=index) for index in range(1, 4)]
    hydrated = {
        item.id: SimpleNamespace(id=item.id, released_definition=None)
        for item in created
    }
    create_workflow = AsyncMock(side_effect=created)
    get_workflow = AsyncMock(
        side_effect=lambda workflow_id, organization_id: hydrated[workflow_id]
    )
    save_draft = AsyncMock()
    publish_draft = AsyncMock()
    monkeypatch.setattr(poc_seed.db_client, "create_workflow", create_workflow)
    monkeypatch.setattr(poc_seed.db_client, "get_workflow", get_workflow)
    monkeypatch.setattr(poc_seed.db_client, "save_workflow_draft", save_draft)
    monkeypatch.setattr(poc_seed.db_client, "publish_workflow_draft", publish_draft)

    result = await poc_seed.seed(organization_id=11, user_id=22)

    assert result == {
        "openai_realtime": 1,
        "gemini_live": 2,
        "google_cascade": 3,
    }
    assert create_workflow.await_count == 3
    assert get_workflow.await_count == 3
    assert all(
        call.kwargs == {"organization_id": 11} for call in get_workflow.await_args_list
    )
    assert save_draft.await_count == 3
    assert publish_draft.await_count == 3


def test_workflow_json_has_staged_support_flow_and_scoped_tools():
    tool_uuids = {
        "get_caller": "tool-get-caller",
        "get_my_tickets": "tool-get-my-tickets",
        "get_ticket_details": "tool-get-ticket-details",
        "get_ticket_summary": "tool-get-ticket-summary",
        "prepare_support_ticket": "tool-prepare-ticket",
        "create_support_ticket": "tool-create-ticket",
        "transfer_to_anurag": "tool-transfer",
        "end_call": "tool-end-call",
    }

    workflow = poc_seed._workflow_json(tool_uuids, "Hello from the selected model.")
    WorkflowGraph(ReactFlowDTO.model_validate(workflow))
    nodes = {node["id"]: node for node in workflow["nodes"]}

    assert set(nodes) == {
        "start",
        "triage",
        "existing-ticket",
        "new-ticket",
        "human",
        "close",
        "failure",
        "global",
    }
    assert nodes["start"]["data"]["tool_uuids"] == [
        "tool-get-caller",
        "tool-end-call",
    ]
    assert nodes["triage"]["data"]["tool_uuids"] == ["tool-end-call"]
    assert nodes["existing-ticket"]["data"]["tool_uuids"] == [
        "tool-get-my-tickets",
        "tool-get-ticket-details",
        "tool-get-ticket-summary",
        "tool-end-call",
    ]
    assert nodes["new-ticket"]["data"]["tool_uuids"] == [
        "tool-prepare-ticket",
        "tool-create-ticket",
        "tool-end-call",
    ]
    assert nodes["human"]["data"]["tool_uuids"] == [
        "tool-transfer",
        "tool-end-call",
    ]
    assert nodes["close"]["data"]["name"] == "Successful completion"
    assert nodes["failure"]["data"]["name"] == "Unable to complete"
    assert all(edge["type"] == "custom" for edge in workflow["edges"])
    assert all(edge["data"]["condition"] for edge in workflow["edges"])
    assert {
        edge["source"] for edge in workflow["edges"] if edge["target"] == "failure"
    } == {"start", "triage", "existing-ticket", "new-ticket", "human"}
    assert len(workflow["edges"]) == 19


def test_openai_poc_uses_automatic_transcription_language_detection():
    realtime = poc_seed.STACKS["poc-openai"]["model_overrides"]["realtime"]

    assert realtime["language"] is None


@pytest.mark.asyncio
async def test_sync_tools_repairs_end_call_description(monkeypatch):
    names = [
        *(f"POC {function}" for function in poc_seed.NATIVE_FUNCTIONS),
        "POC Transfer to Anurag",
        "POC End Call",
    ]
    existing = [
        SimpleNamespace(name=name, tool_uuid=f"tool-{index}")
        for index, name in enumerate(names)
    ]
    update_tool = AsyncMock(
        side_effect=lambda tool_uuid, organization_id, **kwargs: SimpleNamespace(
            tool_uuid=tool_uuid
        )
    )
    monkeypatch.setattr(
        poc_seed.db_client,
        "get_tools_for_organization",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(poc_seed.db_client, "update_tool", update_tool)

    await poc_seed._sync_tools(organization_id=11, user_id=22)

    end_call_update = next(
        call
        for call in update_tool.await_args_list
        if call.args[0] == existing[-1].tool_uuid
    )
    assert "hang up" in end_call_update.kwargs["description"]
    assert "invoke this tool" in end_call_update.kwargs["description"]
