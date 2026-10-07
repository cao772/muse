import asyncio

import httpx2 as httpx
import pytest

from integrations import cao

PROJECTS = [
    {
        "project_id": "kb-platform",
        "project_name": "法规知识库平台",
        "attention_workspace_count": 0,
    },
    {
        "project_id": "defect-agent",
        "project_name": "电力设备缺陷处置",
        "attention_workspace_count": 1,
    },
]


def transport(status=200):
    def handler(request):
        if status != 200:
            return httpx.Response(status, json={"detail": "private"})
        if request.url.path == "/api/v1/projects":
            return httpx.Response(200, json=PROJECTS)
        if request.url.path == "/api/v1/projects/kb-platform/brief":
            return httpx.Response(
                200,
                json={
                    "current_stage": "开发联调与验证",
                    "recorded_stage": {"stage": "Stage50 深采集验证"},
                    "in_progress": ["扩展真实新站迁移样本并核对复用策略"],
                    "issues": ["剩余受限站点仍需账号或授权"],
                    "next_steps": ["继续扩大真实新站迁移样本"],
                },
            )
        raise AssertionError(request.url.path)

    return httpx.MockTransport(handler)


def test_cao_requires_loopback_http():
    cao.CAOClient("http://127.0.0.1:8080")
    cao.CAOClient("http://localhost:8080")
    with pytest.raises(ValueError):
        cao.CAOClient("https://127.0.0.1:8080")
    with pytest.raises(ValueError):
        cao.CAOClient("http://192.168.1.10:8080")
    with pytest.raises(ValueError):
        cao.CAOClient("http://127.0.0.1:8080/api")


def test_portfolio_and_specific_project_answers_are_bounded():
    async def check():
        client = cao.CAOClient("http://127.0.0.1:8080", transport=transport())
        portfolio = await client.answer("Muse，我现在有哪些项目？")
        assert "2个项目" in portfolio
        assert "法规知识库平台" in portfolio

        status = await client.answer("法规知识库项目现在进展怎么样？")
        assert "Stage50 深采集验证" in status
        assert "正在做" in status
        assert "下一步" in status
        assert len(status) <= 120

        next_step = await client.answer("法规知识库项目下一步是什么？")
        assert "继续扩大真实新站迁移样本" in next_step
        assert len(next_step) <= 120

        risk = await client.answer("法规知识库项目现在有什么风险？")
        assert "账号或授权" in risk
        assert len(risk) <= 120

    asyncio.run(check())


def test_non_project_query_falls_back_without_calling_cao():
    class Fallback:
        async def reply(self, text):
            return "普通回答"

    class Never:
        async def answer(self, text):
            raise AssertionError("CAO should not be called")

    async def check():
        provider = cao.ProjectAwareProvider(Fallback(), Never())
        assert await provider.reply("给我讲个笑话") == "普通回答"
        assert provider.last_source == "llm"

    asyncio.run(check())


def test_project_query_does_not_leak_cao_error_body():
    class Fallback:
        async def reply(self, text):
            raise AssertionError("project query must not fall back to ungrounded LLM")

    async def check():
        client = cao.CAOClient("http://127.0.0.1:8080", transport=transport(503))
        provider = cao.ProjectAwareProvider(Fallback(), client)
        answer = await provider.reply("法规知识库项目进展怎么样？")
        assert answer == "CAO 项目中枢暂时不可用，请稍后再试。"
        assert "private" not in answer
        assert provider.last_source == "cao"

    asyncio.run(check())


def test_invalid_project_payload_is_rejected():
    def handler(request):
        return httpx.Response(200, json={"unexpected": True})

    async def check():
        client = cao.CAOClient(
            "http://127.0.0.1:8080",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(cao.CAOError):
            await client.list_projects()

    asyncio.run(check())
