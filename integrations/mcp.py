"""Future MCP client boundary. No tools are connected or executed in Stage 0."""

from typing import Protocol


class ToolAdapter(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, object]) -> object: ...
