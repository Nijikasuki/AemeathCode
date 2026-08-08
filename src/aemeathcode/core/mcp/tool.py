from aemeathcode.agent.tools.base import BaseTool, ToolResult


class MCPTool(BaseTool):
    def __init__(self, client, tool_def):
        self._client = client
        self.name = tool_def["name"]                     # ← 实例属性,不是类属性
        self.description = tool_def.get("description", "")
        self.input_schema = tool_def.get("inputSchema", {})   # MCP 叫 inputSchema → 你的 input_schema,翻译

    async def invoke(self, params, ctx):
        result = await self._client.call_tool(self.name, params)
        text = "".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")
        return ToolResult(content=text, is_error=result.get("isError", False))