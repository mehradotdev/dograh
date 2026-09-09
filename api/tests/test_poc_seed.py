from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.poc import seed as poc_seed


@pytest.mark.asyncio
async def test_seed_refetches_new_workflows_before_reading_definitions(monkeypatch):
    monkeypatch.setattr(poc_seed, "_sync_tools", AsyncMock(return_value=["tool-1"]))
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
        call.kwargs == {"organization_id": 11}
        for call in get_workflow.await_args_list
    )
    assert save_draft.await_count == 3
    assert publish_draft.await_count == 3
