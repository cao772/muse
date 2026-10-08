"""Voice intents call CAO only; this module has no Host/CLI/shell dependency."""

from __future__ import annotations

import re
from uuid import UUID, uuid4

import httpx2 as httpx

from integrations.cao import CAOClient, CAOError, ProjectAwareProvider

PREFIX = "/api/v1/personal/execution"
PROFILES = {
    "快一点": "fast",
    "快速": "fast",
    "快模型": "fast",
    "强模型": "strong",
    "强一点": "strong",
    "均衡": "balanced",
}


def intent(text: str, active=False) -> str | None:
    lower = text.lower()
    for alias in ("code x", "codecs", "科德克斯", "扣得克斯"):
        lower = lower.replace(alias, "codex")
    if any(x in lower for x in ("告诉codex", "告诉 codex", "刚才那个方案", "追加反馈")):
        return "feedback"
    if any(
        x in lower
        for x in ("让codex", "让 codex", "启动codex", "启动 codex", "开始开发", "启动开发任务")
    ):
        return "launch"
    if any(x in text for x in PROFILES) or "高推理" in text or "低推理" in text:
        return "profile"
    if (
        "codex" in lower
        or "当前用什么模型" in text
        or (
            active
            and any(
                x in text
                for x in (
                    "做到哪",
                    "开发到哪",
                    "什么模型",
                    "推理",
                    "测试过",
                    "阻塞",
                    "查询结果",
                    "开发结果",
                )
            )
        )
    ):
        return "query"
    return None


class ExecutionClient(CAOClient):
    def __init__(self, base_url, token, timeout_seconds=60, *, transport=None):
        super().__init__(base_url, timeout_seconds, transport=transport)
        self.token = token

    async def request(self, method, path, body=None):
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.request(
                    method,
                    self.base_url + PREFIX + path,
                    headers={"X-Muse-Token": self.token},
                    json=body,
                )
            if response.status_code not in {200, 201}:
                raise CAOError("CAO execution unavailable or rejected")
            result = response.json()
            if not isinstance(result, dict):
                raise CAOError("Invalid CAO execution response")
            return result
        except CAOError:
            raise
        except Exception:
            # No mutation retries, including caller cancellation/timeouts.
            raise CAOError("CAO execution outcome unconfirmed; do not replay") from None

    async def projects(self):
        # Project rollups can exceed the short P1 query timeout; no mutation or retry.
        return await self.list_projects()

    async def provider(self):
        return await self.request("GET", "/provider")

    async def inspect(self, execution_id):
        return await self.request("GET", f"/runs/{UUID(execution_id)}")


class PersonalAgentRouter(ProjectAwareProvider):
    def __init__(self, fallback, cao, execution):
        super().__init__(fallback, cao)
        self.execution = execution
        self.active_id = None
        self.snapshot = None
        self.profile = "balanced"
        self.effort = "medium"
        self.on_execution = lambda value: None
        self.launch_pending = False
        self.last_intent = "chat"
        self.last_route_result = "none"

    def publish(self, value):
        if self.snapshot and self.snapshot.get("id") == value.get("id"):
            value = {**self.snapshot, **value}
        self.snapshot = value
        self.on_execution(value)

    def choose(self, text):
        profile = next((v for k, v in PROFILES.items() if k in text), self.profile)
        effort = (
            "high"
            if "高推理" in text
            else "low"
            if "低推理" in text
            else "medium"
            if "中推理" in text
            else self.effort
        )
        return profile, effort

    def timeout_seconds(self, text, default):
        if intent(text, bool(self.active_id)):
            return max(default, 120)
        timeout = getattr(self.fallback, "timeout_seconds", None)
        return timeout(text, default) if callable(timeout) else default

    async def restore(self, execution_id):
        # Explicit operator recovery: inspect one authorized UUID; never launch/resume a harness.
        value = await self.execution.inspect(str(UUID(execution_id)))
        self.active_id = str(UUID(execution_id))
        self.publish(value)

    async def refresh(self):
        if self.launch_pending:
            return self.snapshot
        if self.active_id:
            value = await self.execution.inspect(self.active_id)
            self.publish(value)
            return value
        return None

    async def reply(self, text):
        action = intent(text, bool(self.active_id))
        self.last_intent = action or "chat"
        self.last_route_result = "handled"
        if not action:
            if hasattr(self.fallback, "last_route_reason"):
                answer = await self.fallback.reply(text)
                self.last_source = self.fallback.last_source
                return answer
            return await super().reply(text)
        self.last_source = "cao"
        try:
            if action == "profile":
                self.profile, self.effort = self.choose(text)
                return f"下一项任务使用{self.profile}档位，{self.effort}推理。已有会话不变更模型。"
            if action == "launch":
                if self.active_id:
                    current = await self.refresh()
                    if current["status"] not in {"finished", "failed"}:
                        return "已有 Codex 任务，请先查询或追加反馈，不重复启动。"
                projects = await self.execution.projects()
                # Execution requires an explicit unambiguous name/ID, never fuzzy guess.
                norm = re.sub(r"[\W_]+", "", text.lower())
                matches = []
                for p in projects:
                    names = (p["project_name"], p["project_id"])
                    candidates = [
                        re.sub(r"[\W_]+", "", n.lower()).removesuffix("平台").removesuffix("项目")
                        for n in names
                    ]
                    if any(n and n in norm for n in candidates):
                        matches.append(p)
                if len(matches) != 1:
                    self.last_route_result = "ambiguous_project"
                    return "请说清唯一的 CAO 项目全名，我不会猜仓库。"
                project = matches[0]
                task_text = text.lower()
                for name in (project["project_name"], project["project_id"]):
                    task_text = task_text.replace(name.lower(), "")
                task_text = re.sub(r"开始开发|启动开发任务|让\s*codex|启动\s*codex", "", task_text)
                if not re.search(
                    r"写|实现|修复|检查|测试|重构|更新|优化|新增|添加|排查|修改|分析|运行",
                    task_text,
                ):
                    self.last_route_result = "missing_task"
                    return (
                        "项目已识别，但没收到具体任务。请用短句说项目和要做的事，"
                        "不会按仓库默认任务启动。"
                    )
                provider = await self.execution.provider()
                bindings = [
                    b
                    for b in provider.get("bindings", [])
                    if b.get("project_id") == project["project_id"]
                ]
                if len(bindings) != 1:
                    return "该项目没有唯一授权仓库，请先在 CAO 配置仓库绑定。"
                profile, effort = self.choose(text)
                if profile not in provider.get("model_profiles", {}):
                    return "本机尚未配置这个模型档位。"
                request_id = str(uuid4())
                # Remember the ID BEFORE mutation; lost responses can be queried, never repeated.
                self.active_id = request_id
                self.publish(
                    {
                        "id": request_id,
                        "status": "starting",
                        "model_profile": profile,
                        "task_title": project["project_name"],
                    }
                )
                self.launch_pending = True
                try:
                    result = await self.execution.request(
                        "POST",
                        "/runs",
                        {
                            "request_id": request_id,
                            "project_id": project["project_id"],
                            "repository_id": bindings[0]["repository_id"],
                            "task_id": "P2-" + request_id,
                            "task_title": project["project_name"] + "开发任务",
                            "prompt": text,
                            "agent": "codex",
                            "model_profile": profile,
                            "reasoning_effort": effort,
                        },
                    )
                finally:
                    self.launch_pending = False
                self.publish(result)
                if result["status"] in {"failed", "unknown"}:
                    return "Codex 启动未确认，请查询执行记录，不会自动重试。"
                return f"Codex 已开始，{profile}档位，{effort}推理。"
            if not self.active_id:
                self.last_route_result = "no_active_execution"
                return "当前没有 Muse 启动的 Codex 任务，请先说项目名称启动。"
            current = await self.refresh()
            if action == "feedback":
                if current["status"] not in {"running", "waiting"}:
                    return "当前会话不是可反馈状态，不会重启或重放。"
                result = await self.execution.request(
                    "POST",
                    f"/runs/{UUID(self.active_id)}/feedback",
                    {"request_id": str(uuid4()), "text": text},
                )
                return (
                    "反馈已发送给当前 Codex。"
                    if result.get("status") == "sent"
                    else "反馈结果未确认，不会重复发送。"
                )
            if "模型" in text or "推理" in text:
                return (
                    f"当前{current.get('model_profile', '未知')}档位，"
                    f"{current.get('reasoning_effort', '未知')}推理。"
                )
            if "测试" in text:
                passed, failed = current.get("tests_passed"), current.get("tests_failed")
                return (
                    f"实际测试{passed}通过，{failed}失败。"
                    if passed is not None and failed is not None
                    else "尚未收到当前会话的真实测试事件。"
                )
            summary = str(current.get("safe_summary") or "执行状态未确认")[:80]
            progress = str(current.get("latest_progress") or "")
            return (summary + "。" + progress)[:120]
        except CAOError:
            self.last_route_result = "cao_unavailable"
            if self.active_id:
                self.publish({"id": self.active_id, "status": "unknown"})
            return "CAO 执行中枢暂时不可用，操作未确认，不会自动重试。"
