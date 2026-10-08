from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx


class CAOError(RuntimeError):
    """Sanitized local Project OS error; never exposes response bodies."""


PROJECT_QUERY_MARKERS = (
    "项目",
    "进展",
    "做到哪",
    "做到哪里",
    "下一步",
    "待办",
    "当前阶段",
    "当前状态",
    "风险",
    "阻塞",
    "问题",
    "开发到哪",
    "完成了吗",
    "完成了没",
    "Codex等什么",
    "Codex 等什么",
    "codex等什么",
    "codex 等什么",
    "我刚回来",
    "错过什么",
    "需要我处理",
    "待我确认",
    "悬着",
    "未完成的事",
    "今天最该做",
    "今天先做什么",
    "今天优先做什么",
    "先处理什么",
    "现在最重要",
)
PORTFOLIO_MARKERS = ("有哪些项目", "项目列表", "多少项目", "所有项目", "项目有哪些")
SUMMARY_MARKERS = ("我刚回来", "错过什么", "需要我处理", "待我确认", "今天最该做", "现在最重要")
OPEN_LOOP_MARKERS = ("悬着", "未完成的事", "open loops", "开放事项")
COMPLETION_MARKERS = ("完成了吗", "完成了没", "真的完成", "验收通过了吗")


def _normalize(value: str) -> str:
    text = re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)
    for suffix in ("项目", "平台"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def _short(value: Any, limit: int = 28) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


def looks_like_project_query(text: str) -> bool:
    return any(marker in text for marker in PROJECT_QUERY_MARKERS)


class CAOClient:
    def __init__(
        self, base_url: str, timeout_seconds: float = 5, *, muse_token: str = "", transport=None
    ):
        parsed = urlsplit(base_url.rstrip("/"))
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("CAO base URL must be loopback HTTP without credentials/path/query")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.muse_token = muse_token

    async def _get(self, path: str) -> Any:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(
                    self.base_url + path,
                    headers={"X-Muse-Token": self.muse_token} if self.muse_token else {},
                )
            if response.status_code != 200:
                raise CAOError(f"CAO request failed (HTTP {response.status_code})")
            return response.json()
        except CAOError:
            raise
        except Exception:
            raise CAOError("CAO project service unavailable or returned invalid data") from None

    async def list_projects(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/projects")
        if not isinstance(data, list) or len(data) > 200:
            raise CAOError("CAO project list returned invalid data")
        projects = [
            item
            for item in data
            if isinstance(item, dict)
            and isinstance(item.get("project_id"), str)
            and isinstance(item.get("project_name"), str)
        ]
        if len(projects) != len(data):
            raise CAOError("CAO project list returned invalid data")
        return projects

    async def attention(self) -> dict[str, Any]:
        if not self.muse_token:
            raise CAOError("CAO attention requires a scoped Muse token")
        data = await self._get("/api/v1/personal-agent/attention")
        if not isinstance(data, dict):
            raise CAOError("CAO attention returned invalid data")
        return data

    async def work_brief(self, mode: str) -> dict[str, Any]:
        if mode not in {"return", "priority"}:
            raise ValueError("Invalid work brief mode")
        if not self.muse_token:
            raise CAOError("CAO personal work brief requires a scoped Muse token")
        data = await self._get(f"/api/v1/personal-agent/work-brief?mode={mode}")
        if (
            not isinstance(data, dict)
            or data.get("mode") != mode
            or data.get("snapshot_only") is not True
            or data.get("auto_execute") is not False
            or data.get("comparison_available") is not False
            or not isinstance(data.get("items"), list)
        ):
            raise CAOError("CAO work brief returned invalid or unverified data")
        return data

    async def personal_summary(self) -> dict[str, Any]:
        data = await self._get("/api/v1/personal-agent/summary")
        if not isinstance(data, dict):
            raise CAOError("CAO personal summary returned invalid data")
        return data

    async def open_loops(self) -> dict[str, Any]:
        data = await self._get("/api/v1/personal-agent/open-loops")
        if not isinstance(data, dict):
            raise CAOError("CAO open loops returned invalid data")
        return data

    async def completion(self, project_id: str) -> dict[str, Any]:
        if not project_id or len(project_id) > 200 or "/" in project_id:
            raise ValueError("Invalid CAO project id")
        data = await self._get(f"/api/v1/personal-agent/completion/{project_id}")
        if not isinstance(data, dict):
            raise CAOError("CAO completion judge returned invalid data")
        return data

    async def project_brief(self, project_id: str) -> dict[str, Any]:
        if not project_id or len(project_id) > 200 or "/" in project_id:
            raise ValueError("Invalid CAO project id")
        data = await self._get(f"/api/v1/projects/{project_id}/brief")
        if not isinstance(data, dict):
            raise CAOError("CAO project brief returned invalid data")
        return data

    @staticmethod
    def resolve_project(text: str, projects: list[dict[str, Any]]) -> dict[str, Any] | None:
        query = _normalize(text)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for project in projects:
            names = [str(project.get("project_name") or ""), str(project.get("project_id") or "")]
            best = 0.0
            for name in names:
                candidate = _normalize(name)
                if not candidate:
                    continue
                if candidate in query or query in candidate:
                    best = max(best, 1.0 if candidate in query else 0.9)
                else:
                    best = max(best, SequenceMatcher(None, query, candidate).ratio())
            ranked.append((best, project))
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        score, project = ranked[0]
        if score < 0.62:
            return None
        if len(ranked) > 1 and score - ranked[1][0] < 0.08:
            return None
        return project

    async def answer(self, text: str) -> str | None:
        if not looks_like_project_query(text):
            return None

        lowered = text.lower()
        if "codex" in lowered and "等什么" in text:
            data = await self.attention()
            items = [
                i
                for i in data.get("items", [])
                if i.get("source") == "execution" and i.get("needs_user") is True
            ]
            if not items:
                return "当前快照没有记录 Codex 等待你处理的事项；这不代表任务已正式验收。"
            first = items[0]
            return (
                f"当前快照有{len(items)}项 Codex 事项需要你处理。"
                f"状态：{_short(first.get('execution_status'), 20)}。"
                f"事项：{_short(first.get('text'), 34)}。"
            )

        if any(marker in lowered for marker in OPEN_LOOP_MARKERS):
            data = await self.open_loops()
            count = int(data.get("count") or 0)
            needs_user = int(data.get("needs_user_count") or 0)
            items = list(data.get("items") or [])
            first = _short((items[0] if items else {}).get("text"), 34)
            tail = f"。最优先：{first}" if first else ""
            return f"目前有{count}个未闭环事项，其中{needs_user}个需要你处理{tail}。"

        if any(marker in text for marker in SUMMARY_MARKERS):
            priority_mode = any(
                marker in text
                for marker in (
                    "今天最该做",
                    "今天先做什么",
                    "今天优先做什么",
                    "先处理什么",
                    "现在最重要",
                )
            )
            mode = "priority" if priority_mode else "return"
            data = await self.work_brief(mode)
            headline = _short(data.get("headline"), 52)
            items = data.get("items") or []
            first = items[0] if items and isinstance(items[0], dict) else None
            if first:
                name = _short(first.get("project_name"), 14)
                task = _short(first.get("text"), 30)
                return f"{headline}。先看{name}：{task}。仅为当前记录，不代表最新变化。"
            return f"{headline}。仅为当前记录，不代表最新变化。"

        projects = await self.list_projects()
        if any(marker in text for marker in PORTFOLIO_MARKERS):
            names = [_short(item.get("project_name"), 18) for item in projects[:4]]
            tail = "、".join(name for name in names if name)
            if tail:
                return f"CAO 当前登记{len(projects)}个项目。最近包括：{tail}。"
            return f"CAO 当前登记{len(projects)}个项目。"

        project = self.resolve_project(text, projects)
        if project is None:
            return "CAO 里没找到对应项目，请说项目全名。"

        project_id = str(project["project_id"])
        name = _short(project.get("project_name"), 18)
        if any(marker in text for marker in COMPLETION_MARKERS):
            judgement = await self.completion(project_id)
            verdict = str(judgement.get("verdict") or "insufficient_evidence")
            labels = {
                "tracked_scope_complete": "当前已跟踪范围有正式完成证据",
                "not_complete": "还不能判定完成",
                "attention": "存在失败或阻塞，不能判定完成",
                "insufficient_evidence": "证据不足，不能判定完成",
            }
            unresolved = int(judgement.get("unresolved_work_item_count") or 0)
            return f"{name}：{labels.get(verdict, '还不能判定完成')}，未闭环{unresolved}项。"

        brief = await self.project_brief(project_id)
        recorded = brief.get("recorded_stage") or {}
        stage = _short(recorded.get("stage") or brief.get("current_stage") or "阶段未知", 18)
        in_progress = list(brief.get("in_progress") or [])
        issues = list(brief.get("issues") or [])
        next_steps = list(brief.get("next_steps") or [])

        if any(marker in text for marker in ("风险", "阻塞", "问题")):
            issue = _short(issues[0] if issues else "暂无明确阻塞", 34)
            return f"{name}：当前{stage}。问题：{issue}。"
        if any(marker in text for marker in ("下一步", "待办")):
            next_step = _short(next_steps[0] if next_steps else "暂无明确下一步", 38)
            return f"{name}：当前{stage}。下一步：{next_step}。"

        active = _short(in_progress[0] if in_progress else "暂无明确进行中事项", 30)
        next_step = _short(next_steps[0] if next_steps else "暂无明确下一步", 30)
        return f"{name}：当前{stage}。正在做：{active}。下一步：{next_step}。"


class ProjectAwareProvider:
    def __init__(self, fallback, cao: CAOClient):
        self.fallback = fallback
        self.cao = cao
        self.last_source = "llm"

    async def reply(self, text: str) -> str:
        if looks_like_project_query(text):
            try:
                answer = await self.cao.answer(text)
            except CAOError:
                self.last_source = "cao"
                return "CAO 项目中枢暂时不可用，请稍后再试。"
            if answer is not None:
                self.last_source = "cao"
                return answer
        self.last_source = "llm"
        return await self.fallback.reply(text)
