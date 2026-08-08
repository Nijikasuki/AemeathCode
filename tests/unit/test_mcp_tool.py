"""MCPTool 适配器的单元测试:把 MCP 工具定义包成 BaseTool + invoke 转发。

用 FakeClient 替身:invoke 里 tool 会调 client.call_tool,我们让它返回 canned MCP 结果,
就能验证"翻译 + 抽取 content 文本 + isError 传递",不用真连 MCP server。
"""
from aemeathcode.core.mcp.tool import MCPTool


class FakeClient:
    def __init__(self, result: dict):
        self._result = result
        self.called_with = None

    async def call_tool(self, name, arguments):
        self.called_with = (name, arguments)      # 记下被怎么调的
        return self._result


async def test_translates_tool_def_to_instance_attrs():
    client = FakeClient({"content": [], "isError": False})
    tool = MCPTool(client, {"name": "add", "description": "两数相加",
                            "inputSchema": {"type": "object", "required": ["a"]}})
    assert tool.name == "add"                      # 实例属性(不是类属性)
    assert tool.description == "两数相加"
    assert tool.input_schema == {"type": "object", "required": ["a"]}   # inputSchema → input_schema


async def test_invoke_forwards_and_extracts_text():
    client = FakeClient({"content": [{"type": "text", "text": "hello"}], "isError": False})
    tool = MCPTool(client, {"name": "echo"})       # description/inputSchema 省略 → 默认空

    result = await tool.invoke({"msg": "hi"}, ctx=None)

    assert result.content == "hello"               # 从 content 块抽出文本
    assert result.is_error is False
    assert client.called_with == ("echo", {"msg": "hi"})   # 原样转发给 call_tool


async def test_invoke_propagates_is_error():
    client = FakeClient({"content": [{"type": "text", "text": "boom"}], "isError": True})
    result = await MCPTool(client, {"name": "x"}).invoke({}, ctx=None)
    assert result.is_error is True                 # server 说 isError → ToolResult 也 is_error
