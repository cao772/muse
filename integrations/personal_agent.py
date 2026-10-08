from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from integrations.cao import looks_like_project_query

RouteSource = Literal["cao", "codex", "chatgpt", "commerce", "llm"]

EXPLICIT_GPT_MARKERS = (
    "用gpt",
    "用 GPT",
    "让gpt",
    "让 GPT",
    "chatgpt",
    "认真查",
    "查网页",
    "网上查",
    "联网查",
    "深度研究",
    "深入研究",
    "认真研究",
    "深度思考",
)
REFLECTION_MARKERS = (
    "我没想到",
    "我漏了什么",
    "还有什么没想到",
    "更深的问题",
    "真正的问题",
    "反思一下",
    "换个角度",
)
WEB_MARKERS = (
    "最新",
    "今天",
    "现在网上",
    "网上案例",
    "网页",
    "互联网",
    "查一下",
    "认真查",
    "调研",
    "研究一下",
    "深度研究",
    "认真研究",
)
HIGH_DIFFICULTY_MARKERS = (
    "架构",
    "权衡",
    "方案设计",
    "系统设计",
    "根因",
    "复杂",
    "全面分析",
    "深入分析",
    "长期",
    "风险",
    "取舍",
    "为什么",
    "怎么设计",
    "怎么实现",
)
CODEX_ACTION_MARKERS = (
    "让codex",
    "让 Codex",
    "codex继续",
    "Codex继续",
    "继续开发",
    "开始开发",
    "改代码",
    "修代码",
    "跑测试",
    "codex进度",
    "Codex进度",
    "当前模型",
    "换模型",
    "推理档位",
    "告诉codex",
    "告诉 Codex",
)
COMMERCE_MARKERS = (
    "淘宝",
    "京东",
    "外卖",
    "美团",
    "饿了么",
    "购物车",
    "下单",
    "买一个",
    "买个",
)

PROJECT_FACT_STRONG_MARKERS = (
    "项目",
    "进展",
    "做到哪",
    "做到哪里",
    "下一步",
    "待办",
    "当前阶段",
    "当前状态",
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

REFLECTION_PROMPT = (
    "在我最近反复讨论的问题背后，有没有一个更深的问题，是我一直在绕着它走，却没有真正问出来的？"
)


@dataclass(frozen=True)
class RouteDecision:
    source: RouteSource
    reason: str
    use_web: bool = False
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    reflection: bool = False
    explicit: bool = False


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def difficulty_score(text: str) -> int:
    """Small deterministic heuristic; never sends content to another model just to route it."""
    score = 0
    length = len(text.strip())
    if length >= 70:
        score += 1
    if length >= 140:
        score += 1
    score += min(3, sum(1 for marker in HIGH_DIFFICULTY_MARKERS if marker in text))
    if any(ch in text for ch in ("？", "?")) and ("还是" in text or "对比" in text):
        score += 1
    if "并且" in text or "同时" in text or "综合" in text:
        score += 1
    return score


def route_request(
    text: str,
    *,
    chatgpt_enabled: bool,
    chatgpt_auto_enabled: bool = True,
) -> RouteDecision:
    """Choose the capability layer before any provider sees the request."""
    if _contains(text, CODEX_ACTION_MARKERS):
        return RouteDecision("codex", "explicit_codex_action", explicit=True)

    if looks_like_project_query(text):
        score = difficulty_score(text)
        if _contains(text, PROJECT_FACT_STRONG_MARKERS) or score < 4:
            return RouteDecision("cao", "project_fact_query", explicit=True)

    if _contains(text, COMMERCE_MARKERS):
        return RouteDecision("commerce", "explicit_commerce_action", explicit=True)

    reflection = _contains(text, REFLECTION_MARKERS)
    explicit_gpt = _contains(text, EXPLICIT_GPT_MARKERS)
    use_web = _contains(text, WEB_MARKERS)

    if explicit_gpt or reflection:
        return RouteDecision(
            "chatgpt",
            "explicit_research_or_reflection",
            use_web=use_web,
            reasoning_effort="high" if reflection or "深度" in text or "认真" in text else "medium",
            reflection=reflection,
            explicit=True,
        )

    if chatgpt_enabled and chatgpt_auto_enabled:
        score = difficulty_score(text)
        if score >= 4:
            return RouteDecision(
                "chatgpt",
                f"automatic_high_difficulty:{score}",
                use_web=_contains(text, WEB_MARKERS),
                reasoning_effort="high" if score >= 6 else "medium",
            )

    return RouteDecision("llm", "default_local_or_low_cost_model")


def build_research_input(text: str, decision: RouteDecision) -> str:
    if not decision.reflection:
        return text
    return (
        f"{text}\n\n"
        "请先回答用户当前问题，然后额外用下面这条反思问题检查是否存在被忽略的更深层问题。"
        "只有确实有价值时才指出，不要为了显得深刻而硬找问题。\n"
        f"反思问题：{REFLECTION_PROMPT}"
    )
