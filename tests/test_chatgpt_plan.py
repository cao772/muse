import asyncio
import datetime as dt
import json
import os

import httpx2 as httpx
import pytest

from integrations.chatgpt_plan import ChatGPTPlanError, ChatGPTPlanProvider


def write_credentials(path, *, expired=False):
    saved_at = dt.datetime.now(dt.UTC)
    if expired:
        saved_at -= dt.timedelta(hours=2)
    payload = {
        "client_id": "oaiapp_test",
        "access_token": "access-old",
        "refresh_token": "refresh-old",
        "expires_in": 3600,
        "scopes": [
            "openid",
            "profile",
            "email",
            "offline_access",
            "resource.invoke",
            "chatgpt.tokens.use.direct",
        ],
        "saved_at": saved_at.isoformat(),
    }
    path.write_text(json.dumps(payload))
    os.chmod(path, 0o600)


def test_chatgpt_plan_streams_response_with_web_and_reasoning(tmp_path):
    credential_path = tmp_path / "chatgpt.json"
    write_credentials(credential_path)
    seen = {}

    def handler(request):
        if request.url.path == "/v1/models":
            assert request.headers["authorization"] == "Bearer access-old"
            return httpx.Response(
                200,
                json={"models": [{"slug": "gpt-test", "visibility": "list"}]},
            )
        if request.url.path == "/v1/responses":
            seen["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                text=(
                    "event: response.output_text.delta\n"
                    'data: {"type":"response.output_text.delta","delta":"找到"}\n\n'
                    "event: response.output_text.delta\n"
                    'data: {"type":"response.output_text.delta","delta":"结果"}\n\n'
                    "event: response.completed\n"
                    'data: {"type":"response.completed","response":{"output":[]}}\n\n'
                ),
                headers={"content-type": "text/event-stream"},
            )
        raise AssertionError(str(request.url))

    async def check():
        provider = ChatGPTPlanProvider(
            str(credential_path),
            web_context="low",
            transport=httpx.MockTransport(handler),
            voice_mode=True,
        )
        answer = await provider.reply(
            "认真查一下",
            use_web=True,
            reasoning_effort="high",
        )
        assert answer == "找到结果"
        assert provider.last_model == "gpt-test"
        assert provider.last_used_web is True
        assert provider.last_reasoning_effort == "high"

    asyncio.run(check())
    payload = seen["payload"]
    assert payload["store"] is False
    assert payload["stream"] is True
    assert payload["reasoning"] == {"effort": "high"}
    assert payload["tools"] == [{"type": "web_search", "search_context_size": "low"}]
    assert payload["tool_choice"] == "required"


def test_chatgpt_plan_refreshes_rotating_token(tmp_path):
    credential_path = tmp_path / "chatgpt.json"
    write_credentials(credential_path, expired=True)
    refresh_calls = []

    def handler(request):
        if request.url.host == "auth.openai.com":
            refresh_calls.append(request)
            return httpx.Response(
                200,
                json={
                    "access_token": "access-new",
                    "refresh_token": "refresh-new",
                    "expires_in": 3600,
                    "scope": (
                        "openid profile email offline_access resource.invoke "
                        "chatgpt.tokens.use.direct"
                    ),
                },
            )
        if request.url.path == "/v1/models":
            assert request.headers["authorization"] == "Bearer access-new"
            return httpx.Response(
                200,
                json={"models": [{"slug": "gpt-test", "visibility": "list"}]},
            )
        if request.url.path == "/v1/responses":
            assert request.headers["authorization"] == "Bearer access-new"
            return httpx.Response(
                200,
                text=(
                    'data: {"type":"response.output_text.delta","delta":"好"}\n\n'
                    'data: {"type":"response.completed","response":{"output":[]}}\n\n'
                ),
            )
        raise AssertionError(str(request.url))

    async def check():
        provider = ChatGPTPlanProvider(
            str(credential_path),
            transport=httpx.MockTransport(handler),
        )
        assert await provider.reply("问题") == "好"

    asyncio.run(check())
    assert len(refresh_calls) == 1
    saved = json.loads(credential_path.read_text())
    assert saved["access_token"] == "access-new"
    assert saved["refresh_token"] == "refresh-new"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions")
def test_chatgpt_plan_rejects_broad_credential_permissions(tmp_path):
    credential_path = tmp_path / "chatgpt.json"
    write_credentials(credential_path)
    os.chmod(credential_path, 0o644)

    async def check():
        provider = ChatGPTPlanProvider(str(credential_path))
        with pytest.raises(ChatGPTPlanError, match="0600"):
            await provider.reply("问题")

    asyncio.run(check())
