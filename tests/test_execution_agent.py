import asyncio
from uuid import uuid4

import httpx2 as httpx
import pytest

from integrations.cao import CAOError
from integrations.execution_agent import ExecutionClient, PersonalAgentRouter, intent


class Fallback:
    async def reply(self, text):
        return "ordinary DeepSeek boundary"


class Projects:
    def __init__(self, duplicate=False):
        self.duplicate = duplicate

    async def list_projects(self):
        p = {"project_id": "test-project", "project_name": "测试项目"}
        return [p, dict(p)] if self.duplicate else [p]

    async def answer(self, text):
        return "P1 project answer"


class Execution:
    def __init__(self, status="waiting", bindings=1):
        self.status = status
        self.posts = []
        self.bindings = bindings

    async def projects(self):
        return await Projects().list_projects()

    async def provider(self):
        return {
            "bindings": [{"project_id": "test-project", "repository_id": "safe-test"}]
            * self.bindings,
            "model_profiles": {"fast": "verified", "balanced": "verified", "strong": "verified"},
        }

    async def request(self, method, path, body=None):
        self.posts.append((path, body))
        if path.endswith("feedback"):
            return {"status": "sent"}
        return {
            "id": body["request_id"],
            "status": "starting",
            "model_profile": body["model_profile"],
        }

    async def inspect(self, execution_id):
        return {
            "id": execution_id,
            "status": self.status,
            "model_profile": "strong",
            "reasoning_effort": "high",
            "tests_passed": None,
            "tests_failed": None,
            "safe_summary": "Codex 等待下一步",
        }


def test_complete_router_launch_query_feedback_and_no_duplicate():
    async def check():
        execution = Execution()
        router = PersonalAgentRouter(Fallback(), Projects(), execution)
        assert "strong" in await router.reply("让 Codex 修复测试项目，用强模型，高推理")
        assert "strong" in await router.reply("当前用什么模型？")
        assert "尚未收到" in await router.reply("测试过了吗？")
        assert "反馈已发送" in await router.reply("告诉 Codex，只修 UI")
        assert "不重复启动" in await router.reply("让 Codex 修复测试项目")
        assert len(execution.posts) == 2
        assert "ordinary" in await router.reply("讲个笑话")
        assert router.last_source == "llm"
        assert await router.reply("测试项目进展怎么样") == "P1 project answer"

    asyncio.run(check())


@pytest.mark.parametrize("duplicate,bindings", [(True, 1), (False, 0), (False, 2)])
def test_ambiguity_never_launches(duplicate, bindings):
    async def check():
        execution = Execution(bindings=bindings)
        execution.projects = Projects(duplicate).list_projects
        router = PersonalAgentRouter(Fallback(), Projects(duplicate), execution)
        await router.reply("让 Codex 修复测试项目")
        assert not execution.posts

    asyncio.run(check())


@pytest.mark.parametrize("status", ["finished", "unknown", "failed"])
def test_non_live_feedback_is_not_replayed(status):
    async def check():
        execution = Execution(status)
        router = PersonalAgentRouter(Fallback(), Projects(), execution)
        router.active_id = str(uuid4())
        assert "不会重启" in await router.reply("告诉 Codex，继续修")
        assert not execution.posts

    asyncio.run(check())


def test_timeout_remembers_launch_id_and_never_falls_back_or_replays():
    class Unknown(Execution):
        async def request(self, method, path, body=None):
            self.posts.append((path, body))
            raise CAOError("private error")

    async def check():
        execution = Unknown(status="unknown")
        router = PersonalAgentRouter(Fallback(), Projects(), execution)
        assert "不会自动重试" in await router.reply("让 Codex 修复测试项目")
        assert router.active_id
        await router.reply("让 Codex 修复测试项目")
        assert len(execution.posts) == 1

    asyncio.run(check())


def test_execution_transport_scoped_token_no_redirect_or_retry():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["X-Muse-Token"] == "muse-scoped-test"
        assert "collector" not in str(request.headers).lower()
        return httpx.Response(307, headers={"location": "http://external.invalid"})

    async def check():
        client = ExecutionClient(
            "http://localhost:8080", "muse-scoped-test", transport=httpx.MockTransport(handler)
        )
        with pytest.raises(CAOError):
            await client.request("POST", "/runs", {"request_id": str(uuid4())})
        assert len(requests) == 1

    asyncio.run(check())


def test_intents_and_preferences_do_not_mutate_running_model():
    assert intent("你好") is None
    assert intent("让 Codex 修复 muse 项目的测试，不要提交") == "launch"
    assert intent("刚才那个方案不对，按来源日期判断") == "feedback"

    async def check():
        execution = Execution()
        router = PersonalAgentRouter(Fallback(), Projects(), execution)
        assert "下一项任务" in await router.reply("这个任务用快一点的")
        assert router.profile == "fast" and not execution.posts

    asyncio.run(check())


def test_voice_aliases_and_model_query_without_active_execution():
    assert intent("让 Code X 在测试项目写加法") == "launch"
    assert intent("开始开发测试项目，写加法") == "launch"
    assert intent("当前用什么模型？") == "query"

    async def check():
        router = PersonalAgentRouter(Fallback(), Projects(), Execution())
        assert "当前没有" in await router.reply("当前用什么模型？")
        assert router.last_source == "cao"
        assert router.last_route_result == "no_active_execution"

    asyncio.run(check())


def test_launch_project_resolution_uses_execution_read_timeout():
    class ShortQuery(Projects):
        async def list_projects(self):
            raise AssertionError("Do not use P1 short project timeout for a launch")

    async def check():
        router = PersonalAgentRouter(Fallback(), ShortQuery(), Execution())
        assert "已开始" in await router.reply("开始开发测试项目，写加法")

    asyncio.run(check())


def test_real_progress_remains_within_voice_reply_limit():
    class Progress(Execution):
        async def inspect(self, execution_id):
            result = await super().inspect(execution_id)
            result["latest_progress"] = "实际已完成参数校验，七项测试通过。" * 12
            return result

    async def check():
        router = PersonalAgentRouter(Fallback(), Projects(), Progress())
        router.active_id = str(uuid4())
        answer = await router.reply("Codex 做到哪了？")
        assert "实际已完成" in answer
        assert len(answer) <= 120

    asyncio.run(check())


def test_explicit_restore_only_inspects_authorized_execution():
    async def check():
        execution = Execution()
        router = PersonalAgentRouter(Fallback(), Projects(), execution)
        eid = str(uuid4())
        await router.restore(eid)
        assert router.active_id == eid and not execution.posts
        assert "strong" in await router.reply("当前用什么模型？")
        router.launch_pending = True
        assert await router.refresh() == router.snapshot

    asyncio.run(check())


def test_truncated_launch_does_not_invent_task_from_repository_readme():
    async def check():
        execution = Execution()
        router = PersonalAgentRouter(Fallback(), Projects(), execution)
        assert "没收到具体任务" in await router.reply("开始开发测试项目")
        assert router.last_route_result == "missing_task"
        assert router.active_id is None and not execution.posts

    asyncio.run(check())
