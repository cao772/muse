import asyncio

import httpx2 as httpx
import pytest

from integrations.attention import AttentionObserver
from integrations.cao import CAOClient, CAOError


def snapshot(*ids, truncated=False):
    return dict(
        snapshot_only=True,
        auto_interrupt=False,
        truncated=truncated,
        items=[dict(item_id=i * 24, needs_user=True) for i in ids],
    )


def test_baseline_dedup_clear_and_reappearance():
    observer = AttentionObserver()
    assert observer.observe(snapshot("a")) == []
    assert observer.observe(snapshot("a", "b")) == [snapshot("b")["items"][0]]
    assert observer.observe(snapshot("a", "b")) == []
    observer.observe(snapshot("a"))
    assert observer.observe(snapshot("a", "b"))
    assert observer.is_fresh()


def test_focus_dnd_truncation_and_invalid_snapshots():
    observer = AttentionObserver()
    assert not observer.is_fresh()
    observer.observe(snapshot("a"))
    assert observer.observe(snapshot("b"), focus=True) == []
    assert observer.observe(snapshot("b")) == []
    assert observer.observe(snapshot("c"), do_not_disturb=True) == []
    assert observer.observe(snapshot("c")) == []
    observer.observe(snapshot("d", truncated=True))
    assert observer.observe(snapshot("c", truncated=True)) == []
    with pytest.raises(CAOError):
        observer.observe(dict(items=[]))


def test_attention_requires_token_and_sends_only_to_loopback():
    def handler(request):
        assert request.headers["X-Muse-Token"] == "test-muse-token"
        assert request.url.path == "/api/v1/personal-agent/attention"
        return httpx.Response(200, json=snapshot("a"))

    async def check():
        client = CAOClient(
            "http://127.0.0.1:8080",
            muse_token="test-muse-token",
            transport=httpx.MockTransport(handler),
        )
        assert (await client.attention())["items"]
        with pytest.raises(CAOError):
            await CAOClient("http://127.0.0.1:8080").attention()

    asyncio.run(check())


def test_codex_waiting_query_is_read_only_and_uses_recorded_facts():
    from integrations.personal_agent import route_request

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/personal-agent/attention"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "execution",
                        "needs_user": True,
                        "execution_status": "waiting",
                        "text": "补测试",
                    }
                ]
            },
        )

    async def check():
        client = CAOClient(
            "http://127.0.0.1:8080", muse_token="test-token", transport=httpx.MockTransport(handler)
        )
        assert "waiting" in await client.answer("现在 Codex 等什么")
        assert route_request("现在 Codex 等什么", chatgpt_enabled=True).source == "cao"
        assert route_request("用 GPT 研究 Codex 架构", chatgpt_enabled=True).source == "chatgpt"

    asyncio.run(check())
