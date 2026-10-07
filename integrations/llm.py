from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit

import httpx2 as httpx

if TYPE_CHECKING:
    from gateway.config import Settings


class ProviderError(RuntimeError):
    """Public, sanitized error; never contains upstream bodies or credentials."""


class TextProvider(Protocol):
    async def reply(self, text: str) -> str: ...


class MockProvider:
    async def reply(self, text: str) -> str:
        return f"[mock] 收到：{text}"


class CompatibleProvider:
    def __init__(self, settings: Settings, *, transport=None):
        url = urlsplit(settings.llm_base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("LLM base URL requires HTTPS without credentials/query/fragment")
        if not settings.llm_api_key.get_secret_value():
            raise ValueError("Real provider requires MUSE_LLM_API_KEY")
        if settings.provider == "deepseek" and settings.llm_base_url.rstrip("/") not in {
            "https://api.deepseek.com",
            "https://api.deepseek.com/v1",
        }:
            raise ValueError("DeepSeek provider requires its official API endpoint")
        if settings.provider == "qwen" and url.hostname == "api.deepseek.com":
            raise ValueError("Qwen requires its own explicit base URL and model")
        self.settings = settings
        self.transport = transport

    async def reply(self, text: str) -> str:
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 Muse，请用简洁中文回答。你接收的是文本转录，不能直接听到音频；"
                        "不要声称已经检测麦克风或其他硬件状态。"
                    ),
                },
                {"role": "user", "content": text},
            ],
            "max_tokens": self.settings.llm_max_tokens,
            "stream": False,
        }
        if self.settings.provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.provider_timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self.settings.llm_base_url.rstrip("/") + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + self.settings.llm_api_key.get_secret_value()
                    },
                    json=payload,
                )
                if response.status_code != 200:
                    raise ProviderError(f"LLM request failed (HTTP {response.status_code})")
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("Empty answer")
                return answer.strip()
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("LLM request failed or returned an invalid response") from None


def create_provider(name: str, settings: Settings | None = None) -> TextProvider:
    if name == "mock":
        return MockProvider()
    if name in {"deepseek", "qwen", "openai-compatible"}:
        if settings is None:
            raise ValueError("Real provider requires explicit configuration")
        return CompatibleProvider(settings)
    raise ValueError("Unsupported text provider")
