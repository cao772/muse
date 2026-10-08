from __future__ import annotations

from typing import Any

from integrations.cao import CAOError
from integrations.chatgpt_plan import ChatGPTPlanError
from integrations.personal_agent import build_research_input, route_request


class PersonalAgentProvider:
    """Capability router for Muse voice; providers stay isolated behind narrow adapters."""

    def __init__(
        self,
        fallback,
        *,
        cao=None,
        chatgpt=None,
        codex=None,
        commerce=None,
        chatgpt_auto_enabled: bool = True,
    ):
        self.fallback = fallback
        self.cao = cao
        self.chatgpt = chatgpt
        self.codex = codex
        self.commerce = commerce
        self.chatgpt_auto_enabled = chatgpt_auto_enabled
        self.last_source = "llm"
        self.last_route_reason = "startup"
        self.last_route: dict[str, Any] = {}

    def timeout_seconds(self, text: str, default: float) -> float:
        decision = route_request(
            text,
            chatgpt_enabled=self.chatgpt is not None,
            chatgpt_auto_enabled=self.chatgpt_auto_enabled,
        )
        if decision.source == "chatgpt" and self.chatgpt is not None:
            return max(default, float(getattr(self.chatgpt, "timeout_seconds", default)) + 5)
        return default

    async def reply(self, text: str) -> str:
        decision = route_request(
            text,
            chatgpt_enabled=self.chatgpt is not None,
            chatgpt_auto_enabled=self.chatgpt_auto_enabled,
        )
        self.last_route_reason = decision.reason
        self.last_route = {
            "source": decision.source,
            "reason": decision.reason,
            "use_web": decision.use_web,
            "reasoning_effort": decision.reasoning_effort,
            "reflection": decision.reflection,
            "explicit": decision.explicit,
        }

        if decision.source == "cao":
            if self.cao is None:
                self.last_source = "cao"
                return "CAO 项目中枢还没连接，请先在本机启用。"
            try:
                answer = await self.cao.answer(text)
            except CAOError:
                self.last_source = "cao"
                return "CAO 项目中枢暂时不可用，请稍后再试。"
            self.last_source = "cao"
            return answer or "CAO 当前没有可用结果。"

        if decision.source == "codex":
            self.last_source = "codex"
            if self.codex is None:
                return "Codex 控制还没接通，当前不会假装执行。"
            return await self.codex.reply(text)

        if decision.source == "commerce":
            self.last_source = "commerce"
            if self.commerce is None:
                return "购物和外卖能力还没接通，当前不会代你下单。"
            return await self.commerce.reply(text)

        if decision.source == "chatgpt":
            if self.chatgpt is None:
                self.last_source = "chatgpt"
                if decision.explicit:
                    return "ChatGPT Plus 研究脑还没连接，请先完成授权。"
                self.last_source = "llm"
                return await self.fallback.reply(text)
            try:
                answer = await self.chatgpt.reply(
                    build_research_input(text, decision),
                    use_web=decision.use_web,
                    reasoning_effort=decision.reasoning_effort,
                    reflection=decision.reflection,
                )
            except ChatGPTPlanError:
                if decision.explicit:
                    self.last_source = "chatgpt"
                    return "ChatGPT Plus 研究脑暂时不可用，请稍后再试。"
                self.last_source = "llm"
                return await self.fallback.reply(text)
            self.last_source = "chatgpt"
            return answer

        self.last_source = "llm"
        return await self.fallback.reply(text)
