"""Focused tests for Asterisk ARI call origination."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from api.services.telephony.providers.ari.provider import ARIProvider


class _Response:
    status = 200

    async def text(self):
        return json.dumps({"id": "destination-channel", "state": "Down"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Session:
    def __init__(self):
        self.post = Mock(return_value=_Response())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_transfer_call_forwards_original_caller_id():
    provider = ARIProvider(
        {
            "ari_endpoint": "http://asterisk:8088",
            "app_name": "dograh",
            "app_password": "secret",
        }
    )
    session = _Session()
    manager = AsyncMock()

    with (
        patch(
            "api.services.telephony.providers.ari.provider.aiohttp.ClientSession",
            return_value=session,
        ),
        patch(
            "api.services.telephony.call_transfer_manager.get_call_transfer_manager",
            AsyncMock(return_value=manager),
        ),
    ):
        await provider.transfer_call(
            destination="PJSIP/anurag",
            transfer_id="transfer-id",
            conference_name="unused",
            caller_id="+917065229082",
        )

    assert session.post.call_args.kwargs["params"]["callerId"] == "+917065229082"


@pytest.mark.asyncio
async def test_transfer_call_omits_unknown_caller_id():
    provider = ARIProvider(
        {
            "ari_endpoint": "http://asterisk:8088",
            "app_name": "dograh",
            "app_password": "secret",
        }
    )
    session = _Session()
    manager = AsyncMock()

    with (
        patch(
            "api.services.telephony.providers.ari.provider.aiohttp.ClientSession",
            return_value=session,
        ),
        patch(
            "api.services.telephony.call_transfer_manager.get_call_transfer_manager",
            AsyncMock(return_value=manager),
        ),
    ):
        await provider.transfer_call(
            destination="PJSIP/anurag",
            transfer_id="transfer-id",
            conference_name="unused",
            caller_id="unknown",
        )

    assert "callerId" not in session.post.call_args.kwargs["params"]
