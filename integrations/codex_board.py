"""Bounded read-only Codex board; identifiers never derive from display text."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from integrations.cao import CAOError
from integrations.codex_board_glyphs import GLYPHS

STATES = "running|needs_input|ended_unverified|failed|unknown|stale"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Task(Strict):
    execution_id: str
    repository_id: str = Field(min_length=1, max_length=200)
    title: str = Field(max_length=80)
    state: str = Field(pattern=f"^({STATES})$")
    phase: str | None = Field(default=None, pattern="^(analysis|planning|editing|testing|waiting)$")
    progress: str | None = Field(default=None, max_length=80)
    files: list[str] | None = Field(default=None, max_length=3)
    tests_passed: int | None = Field(default=None, ge=0, le=100000)
    tests_failed: int | None = Field(default=None, ge=0, le=100000)
    test_observed_at: str | None = None
    last_event_at: str | None = None
    model_profile: str | None = Field(default=None, pattern="^(fast|balanced|strong)$")
    reasoning_effort: str | None = Field(default=None, pattern="^(low|medium|high)$")
    source: str = Field(pattern="^(cao_p2|registered_host|codex_desktop)$")
    feedback_allowed: bool
    formal_completion: bool


class Project(Strict):
    project_id: str = Field(min_length=1, max_length=200)
    alias: str = Field(max_length=24)
    tasks: list[Task] = Field(min_length=1, max_length=5)


class Coverage(Strict):
    registered_project_count: int = Field(ge=0, le=10000)
    observed_codex_project_count: int = Field(ge=0, le=50)
    untracked_count: int | None = Field(default=None, ge=0)


class Snapshot(Strict):
    schema_version: int = Field(ge=1, le=1)
    status: str = Field(pattern="^(available|stale|unavailable)$")
    scope_id: str = Field(pattern="^[a-f0-9]{64}$")
    observed_at: str
    coverage: Coverage
    projects: list[Project] = Field(max_length=50)


def validate(data):
    result = Snapshot.model_validate(data)
    at = datetime.fromisoformat(result.observed_at.replace("Z", "+00:00"))
    if at.tzinfo is None or not 0 <= (datetime.now(UTC) - at).total_seconds() <= 30:
        raise ValueError("Stale observation")
    seen, projects = set(), set()
    for project in result.projects:
        if project.project_id in projects:
            raise ValueError("Repeated project")
        projects.add(project.project_id)
        for task in project.tasks:
            identifier = str(UUID(task.execution_id))
            if identifier in seen or task.formal_completion:
                raise ValueError("Invalid task identity/completion")
            seen.add(identifier)
            for stamp in (task.last_event_at, task.test_observed_at):
                if stamp:
                    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    if moment.tzinfo is None or moment > datetime.now(UTC):
                        raise ValueError("Invalid evidence timestamp")

            for value in (task.title, task.progress, project.alias):
                if value and re.search(
                    r"sk-|bearer|token|password|api.?key|secret|cookie|authorization|/Users/|/home/|https?://",
                    value,
                    re.I,
                ):
                    raise ValueError("Private text")
            if task.files and any(
                not re.fullmatch(r"[A-Za-z0-9_./-]{1,64}", p)
                or p.startswith("/")
                or ".." in p.split("/")
                for p in task.files
            ):
                raise ValueError("Private path")
    if len(projects) != result.coverage.observed_codex_project_count:
        raise ValueError("Invalid coverage")
    return result


def display_text(value, limit):
    text = (value or "")[:limit]
    return text if all(c in GLYPHS for c in text) else "详情请在Mac查看"


class CodexBoard:
    def __init__(self, client):
        self.client = client
        self.snapshot = None
        self.project_index = self.task_index = 0
        self.revision = 0
        self.pending = None
        self.action_state = "idle"
        self.last_success = 0.0
        self.lock = asyncio.Lock()

    @property
    def selected(self):
        if not self.snapshot or not self.snapshot.projects:
            return None
        p = self.snapshot.projects[self.project_index]
        return p, p.tasks[self.task_index]

    async def refresh(self):
        async with self.lock:
            previous = self.selected
            try:
                data = validate(await self.client._get("/api/v1/personal-agent/codex-board"))
                self.snapshot = data
                self.project_index = self.task_index = 0
                if previous:
                    for i, p in enumerate(data.projects):
                        for j, t in enumerate(p.tasks):
                            if (p.project_id, t.execution_id, t.repository_id) == (
                                previous[0].project_id,
                                previous[1].execution_id,
                                previous[1].repository_id,
                            ):
                                self.project_index, self.task_index = i, j
                self.last_success = time.monotonic()
                self.revision += 1
                if self.pending and (
                    not self.selected or self.pending["id"] != self.selected[1].execution_id
                ):
                    self.pending = None
            except (CAOError, ValueError, TypeError):
                self.snapshot = None
                self.pending = None

    def navigate(self, action, revision):
        if self.action_state in {"checking", "sending"}:
            return
        if revision != self.revision or not self.snapshot:
            return
        if action in {"next", "previous"} and self.snapshot.projects:
            self.project_index = (self.project_index + (1 if action == "next" else -1)) % len(
                self.snapshot.projects
            )
            self.task_index = 0
        elif action == "task" and self.selected:
            self.task_index = (self.task_index + 1) % len(self.selected[0].tasks)
        self.pending = None
        if self.action_state == "sent":
            self.action_state = "idle"
        self.revision += 1

    def frame(self):
        if not self.snapshot or time.monotonic() - self.last_success > 30:
            return {"status": "unavailable", "revision": self.revision}
        p, t = self.selected if self.selected else (None, None)
        return {
            "status": self.snapshot.status,
            "action": "confirm" if self.pending else self.action_state,
            "instruction": display_text(self.pending["text"], 80) if self.pending else "",
            "revision": self.revision,
            "projects": len(self.snapshot.projects),
            "registered": self.snapshot.coverage.registered_project_count,
            "index": self.project_index + 1 if p else 0,
            "task_index": self.task_index + 1 if t else 0,
            "tasks": len(p.tasks) if p else 0,
            "alias": display_text(p.alias, 24) if p else "",
            "title": display_text(t.title, 32) if t else "",
            "state": t.state if t else "unknown",
            "progress": display_text(t.progress, 40) if t else "",
            "effort": t.reasoning_effort or "unknown" if t else "unknown",
            "source": t.source if t else "unknown",
            "profile": t.model_profile or "unknown" if t else "unknown",
            "passed": t.tests_passed if t else None,
            "failed": t.tests_failed if t else None,
            "event_age": min(
                9999,
                max(
                    0,
                    int(
                        (
                            datetime.now(UTC)
                            - datetime.fromisoformat(t.last_event_at.replace("Z", "+00:00"))
                        ).total_seconds()
                        // 60
                    ),
                ),
            )
            if t and t.last_event_at
            else None,
            "file": t.files[0] if t and t.files else "",
        }

    def unknown_named_project(self, text):
        codes = re.findall(r"(?<![A-Za-z0-9])P[0-9]{1,3}(?![0-9])", text, re.I)
        aliases = {p.alias.lower() for p in self.snapshot.projects} if self.snapshot else set()
        return any(code.lower() not in aliases for code in codes)

    def query(self, text):
        if not self.snapshot or self.snapshot.status != "available":
            return "Codex 看板暂不可用，不能确认实时进度。"
        if self.unknown_named_project(text):
            return "该项目尚未授权接入，请先核对项目清单。"
        if any(w in text for w in ("所有", "哪些", "多少", "列表", "总览")):
            projects = self.snapshot.projects
            tasks = [t for p in projects for t in p.tasks]
            waiting = sum(t.state == "needs_input" for t in tasks)
            running = sum(t.state == "running" for t in tasks)
            unknown = sum(t.state in {"unknown", "stale"} for t in tasks)
            return (
                f"当前接入{len(projects)}个有会话的项目，共{len(tasks)}项任务。"
                f"已确认{running}项近期运行，{waiting}项等你，另有{unknown}项状态未知。"
                "其他任务的运行状态以执行证据为准，未覆盖数量未知。"
            )

        matches = [
            i
            for i, p in enumerate(self.snapshot.projects)
            if p.alias and p.alias.casefold() in text.casefold()
        ]
        if len(matches) > 1:
            return "匹配到多个项目，请先在屏幕选中具体任务。"
        changed_project = False
        if len(matches) == 1:
            changed_project = matches[0] != self.project_index
            self.project_index = matches[0]
            if changed_project:
                self.task_index = 0
            self.pending = None
            self.revision += 1
        if not self.selected:
            return "尚未接入可查看的 Codex 会话，其他本机任务覆盖数未知。"
        p, t = self.selected
        if len(p.tasks) > 1 and changed_project:
            return f"{p.alias}有{len(p.tasks)}项任务，请在屏幕选择准确会话。"
        if any(w in text.lower() for w in ("模型", "推理", "profile", "reasoning")):
            return (
                f"当前{p.alias}任务的模型档位{t.model_profile or '未知'}，"
                f"推理{t.reasoning_effort or '未知'}。没有记录的数据不会猜测。"
            )
        states = {
            "running": "运行中",
            "needs_input": "等待你",
            "ended_unverified": "执行结束，未正式验收",
            "failed": "失败",
            "unknown": "状态未知",
            "stale": "数据过期",
        }
        tests = (
            f"测试{t.tests_passed}通过，{t.tests_failed}失败。"
            if t.tests_passed is not None and t.tests_failed is not None
            else "暂无真实测试结果。"
        )
        return f"{p.alias}，{t.title}，{states[t.state]}。{t.progress or '暂无详细进度'}。{tests}"[
            :180
        ]

    def propose(self, text):
        if len(text) > 80:
            return "请将反馈缩短到八十字以内，长指令请在 Mac 发送。"
        if display_text(text, 80) != text:
            return "屏幕字库暂不支持完整显示这条指令，请在 Mac 发送。"
        if self.action_state in {"checking", "sending", "unknown"}:
            return "上一项操作仍待核对，不能重复发送。"
        if re.search(r"sk-|bearer|token|password|api.?key|secret|cookie|密码", text, re.I):
            return "指令包含敏感信息，请删除后重新录入。"
        if (
            not self.snapshot
            or self.snapshot.status != "available"
            or not self.selected
            or not self.selected[1].feedback_allowed
        ):
            return "当前任务不具备反馈权限或状态未确认。"
        if self.unknown_named_project(text):
            return "该项目尚未授权接入，未创建指令。"
        p, t = self.selected
        # Named different project never falls through to the currently selected task.
        others = [
            q
            for q in self.snapshot.projects
            if q.alias and q.alias.casefold() in text.casefold() and q.project_id != p.project_id
        ]
        if others:
            return "指令与当前选中项目不一致，请先选择目标会话。"
        self.pending = {
            "id": t.execution_id,
            "project": p.project_id,
            "repo": t.repository_id,
            "text": text,
            "request_id": str(uuid4()),
            "expires": time.monotonic() + 60,
        }
        return f"准备向{p.alias}的{t.title}发送：{text[:70]}。请说确认发送，或取消。"

    async def confirm(self, execution):
        pending, self.pending = self.pending, None  # consume before any network request
        if not pending or pending["expires"] < time.monotonic():
            return "没有有效的待确认指令。"
        self.action_state = "checking"
        await self.refresh()
        if not self.selected or not self.snapshot or self.snapshot.status != "available":
            self.action_state = "idle"
            return "目标状态未知，未发送。"
        p, t = self.selected
        if (p.project_id, t.execution_id, t.repository_id) != (
            pending["project"],
            pending["id"],
            pending["repo"],
        ) or not t.feedback_allowed:
            self.action_state = "idle"
            return "目标或权限已经变化，未发送。"
        current = await execution.inspect(t.execution_id)
        if (current.get("project_id"), current.get("repository_id")) != (
            p.project_id,
            t.repository_id,
        ):
            self.action_state = "idle"
            return "会话授权绑定不一致，未发送。"
        self.action_state = "sending"
        try:
            result = await execution.request(
                "POST",
                f"/runs/{UUID(t.execution_id)}/feedback",
                {"request_id": pending["request_id"], "text": pending["text"]},
            )
        except CAOError:
            self.action_state = "unknown"
            raise
        self.action_state = "sent" if result.get("status") == "sent" else "unknown"
        return (
            "反馈已接收，等待真实执行进展。"
            if result.get("status") == "sent"
            else "发送结果未知，不会重试。"
        )
