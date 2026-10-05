from typing import Protocol


class TextProvider(Protocol):
    async def reply(self, text: str) -> str: ...


class MockProvider:
    async def reply(self, text: str) -> str:
        return f"[mock] 收到：{text}"


def create_provider(name: str) -> TextProvider:
    if name == "mock":
        return MockProvider()
    raise ValueError(f"Provider {name!r} is not implemented; use MUSE_PROVIDER=mock in Stage 0")
