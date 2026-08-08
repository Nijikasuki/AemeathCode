"""Agent.loop(ReAct 主循环)的单元测试。

核心手法:**假 provider**。真 provider 要连 LLM,测试里不能连——造个 FakeProvider,
chat() 按预先排好的脚本一条条返回 LlmResponse。这样就能确定性地驱动 loop 走各分支:
  - 直接 end_turn → 该收尾成 success、最终文本进 messages
  - 先 tool_use(调工具)、再 end_turn → 工具真被调、第二轮收尾
"""
from types import SimpleNamespace

from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.llm.types import LlmResponse, ToolCallBlock
from aemeathcode.agent.loop import Agent
from aemeathcode.agent.tools.base import BaseTool, ToolResult
from aemeathcode.agent.tools.registry import ToolRegistry
from aemeathcode.core.context import ExecutionContext
from aemeathcode.core.permissions.manager import PermissionResult


class FakeProvider:
    """按脚本返回 LlmResponse 的假 provider。model 属性 loop 会读(判压缩/窗口)。"""
    model = "fake"

    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, messages, tool_schemas, bus, run_id):
        return self._responses.pop(0)


class EchoTool(BaseTool):
    def __init__(self):
        self.name = "echo"
        self.description = "d"
        self.input_schema = {"type": "object"}
        self.calls = 0

    async def invoke(self, params, ctx):
        self.calls += 1
        return ToolResult(content="echoed")


def _services(allowed=True):
    """tool_use 路径会走 invoke_tool → 权限检查;给个放行的假 services。"""
    class PM:
        async def check(self, tool, params, approver, run_id):
            return PermissionResult(allowed)

    return SimpleNamespace(permission_manager=PM(), approver=None, trace=None)


def _ctx(services=None):
    return ExecutionContext(goal="hi", max_steps=5, run_id="r",
                            tasks=None, messages=[], services=services)


async def test_loop_end_turn_marks_success():
    ctx = _ctx()   # end_turn 路径不碰 services
    provider = FakeProvider([LlmResponse(stop_reason="end_turn", text="done")])
    agent = Agent(ctx=ctx, provider=provider, registry=ToolRegistry(), bus=EventBus(), compactor=None)

    await agent.loop()

    assert ctx.status == "success"
    # 最终文本作为 assistant 消息进了 messages
    assert any(b.get("text") == "done" for b in ctx.messages[-1]["content"])


async def test_loop_tool_use_then_end_turn():
    ctx = _ctx(services=_services(allowed=True))
    tool = EchoTool()
    registry = ToolRegistry()
    registry.register(tool)
    provider = FakeProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[ToolCallBlock("call-1", "echo", {})]),  # 第一轮:调 echo
        LlmResponse(stop_reason="end_turn", text="all done"),                                    # 第二轮:收尾
    ])
    agent = Agent(ctx=ctx, provider=provider, registry=registry, bus=EventBus(), compactor=None)

    await agent.loop()

    assert tool.calls == 1           # 工具被调了一次
    assert ctx.status == "success"   # 第二轮 end_turn 收尾成功
    # 历史里应有:goal(user) → assistant(tool_use) → user(tool_result) → assistant(final)
    roles = [m["role"] for m in ctx.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
