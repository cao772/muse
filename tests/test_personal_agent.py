import asyncio

from integrations.personal_agent import REFLECTION_PROMPT, build_research_input, route_request
from integrations.personal_provider import PersonalAgentProvider


def test_routes_project_codex_commerce_and_explicit_gpt():
    assert route_request(
        "法规知识库项目开发到哪了？",
        chatgpt_enabled=True,
    ).source == "cao"
    assert route_request(
        "让 Codex 继续开发法规项目",
        chatgpt_enabled=True,
    ).source == "codex"
    assert route_request(
        "帮我去淘宝看看摄像头",
        chatgpt_enabled=True,
    ).source == "commerce"

    decision = route_request(
        "用 GPT 认真查一下网上有没有类似案例",
        chatgpt_enabled=False,
    )
    assert decision.source == "chatgpt"
    assert decision.explicit is True
    assert decision.use_web is True
    assert decision.reasoning_effort == "high"

    gpt_only = route_request(
        "用 GPT 想一下这个架构",
        chatgpt_enabled=True,
    )
    assert gpt_only.source == "chatgpt"
    assert gpt_only.use_web is False


def test_high_difficulty_auto_routes_only_when_enabled():
    text = "这个系统架构怎么设计，综合考虑长期风险、复杂权衡和实现取舍？"
    automatic = route_request(
        text,
        chatgpt_enabled=True,
        chatgpt_auto_enabled=True,
    )
    assert automatic.source == "chatgpt"
    assert automatic.explicit is False

    disabled = route_request(
        text,
        chatgpt_enabled=True,
        chatgpt_auto_enabled=False,
    )
    assert disabled.source == "llm"


def test_reflection_prompt_is_only_added_for_reflection_mode():
    decision = route_request(
        "看看我还有什么没想到的功能",
        chatgpt_enabled=True,
    )
    assert decision.source == "chatgpt"
    assert decision.reflection is True
    expanded = build_research_input("看看我还有什么没想到的功能", decision)
    assert REFLECTION_PROMPT in expanded

    plain = route_request("普通问题", chatgpt_enabled=True)
    assert build_research_input("普通问题", plain) == "普通问题"


def test_personal_provider_does_not_fake_unconnected_actions():
    class Fallback:
        async def reply(self, text):
            return "fallback"

    async def check():
        provider = PersonalAgentProvider(Fallback())
        assert (\n            await provider.reply("让 Codex 帮我改代码")\n            == "Codex 控制还没接通，当前不会假装执行。"\n        )
        assert provider.last_source == "codex"
        assert (\n            await provider.reply("淘宝帮我买个摄像头")\n            == "购物和外卖能力还没接通，当前不会代你下单。"\n        )
        assert provider.last_source == "commerce"
        assert (\n            await provider.reply("用 GPT 认真查一下")\n            == "ChatGPT Plus 研究脑还没连接，请先完成授权。"\n        )
        assert provider.last_source == "chatgpt"
        assert await provider.reply("讲个笑话") == "fallback"
        assert provider.last_source == "llm"

    asyncio.run(check())


def test_personal_provider_passes_research_mode_to_chatgpt():
    class Fallback:
        async def reply(self, text):
            raise AssertionError("explicit GPT route must not use fallback")

    class ChatGPT:
        def __init__(self):
            self.call = None

        async def reply(self, text, **kwargs):
            self.call = (text, kwargs)
            return "研究结果"

    async def check():
        chatgpt = ChatGPT()
        provider = PersonalAgentProvider(Fallback(), chatgpt=chatgpt)
        answer = await provider.reply("看看我还有什么没想到的功能")
        assert answer == "研究结果"
        assert provider.last_source == "chatgpt"
        text, kwargs = chatgpt.call
        assert REFLECTION_PROMPT in text
        assert kwargs["reflection"] is True
        assert kwargs["reasoning_effort"] == "high"

    asyncio.run(check())
