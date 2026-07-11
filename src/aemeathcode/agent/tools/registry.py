from aemeathcode.agent.tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def tool_schemas(self) -> list[dict[str, object]]:
        tools = []
        for tool in self._tools.values():
            tools.append({"name": tool.name, "description": tool.description, "input_schema": tool.input_schema})
        return tools
