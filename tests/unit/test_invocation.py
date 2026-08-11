"""invoke_tool 的单元测试:未知工具 / 缺参 / 权限闸门 / 放行才真跑。

【新点:用 SimpleNamespace 造轻量假 ctx】
invoke_tool 只用到 ctx.run_id 和 ctx.services 的 permission_manager/approver/trace,
不必造真的 ExecutionContext——用 SimpleNamespace 拼个最小替身就够,又快又不牵扯别的。
"""
from types import SimpleNamespace

from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.llm.types import ToolCallBlock
from aemeathcode.agent.tools.base import BaseTool, ToolResult
from aemeathcode.agent.tools.invocation import invoke_tool
from aemeathcode.agent.tools.registry import ToolRegistry
from aemeathcode.core.permissions.manager import PermissionResult


class DummyTool(BaseTool):
    def __init__(self, name: str, required=None):
        self.name = name
        self.description = "d"
        self.input_schema = {"type": "object", "required": required or []}
        self.invoked = False          # 记录到底进没进 invoke

    async def invoke(self, params, ctx):
        self.invoked = True
        return ToolResult(content="done")


def _ctx(allowed: bool = True):
    """假 ctx:permission_manager.check 按 allowed 返回放行/拒绝。"""
    class PM:
        async def check(self, tool, params, approver, run_id):
            return PermissionResult(True) if allowed else PermissionResult(False, "拒了")

    services = SimpleNamespace(permission_manager=PM(), approver=None, trace=None)
    return SimpleNamespace(run_id="r1", services=services)


def _recorder(bus: EventBus) -> list:
    """把 bus 上跑过的事件按顺序收下来,用来断言 start/finish 的次序。"""
    seen = []

    async def handler(event):
        seen.append(event)

    bus.subscribe(handler)
    return seen


async def test_unknown_tool():
    result = await invoke_tool(registry=ToolRegistry(), tool_call=ToolCallBlock("1", "nope", {}),
                               bus=EventBus(), ctx=_ctx())
    assert result.is_error and result.error_type == "unknown_tool"


async def test_missing_required_param():
    r = ToolRegistry()
    r.register(DummyTool("foo", required=["x"]))
    result = await invoke_tool(registry=r, tool_call=ToolCallBlock("1", "foo", {}),   # 没给 x
                               bus=EventBus(), ctx=_ctx())
    assert result.is_error and result.error_type == "schema_error"


async def test_permission_denied_skips_invoke():
    r = ToolRegistry()
    t = DummyTool("foo")
    r.register(t)
    result = await invoke_tool(registry=r, tool_call=ToolCallBlock("1", "foo", {}),
                               bus=EventBus(), ctx=_ctx(allowed=False))
    assert result.is_error and result.error_type == "permission_denied"
    assert t.invoked is False          # 权限拒绝 → 根本【没进】invoke


async def test_allowed_runs_tool():
    r = ToolRegistry()
    t = DummyTool("foo")
    r.register(t)
    result = await invoke_tool(registry=r, tool_call=ToolCallBlock("1", "foo", {}),
                               bus=EventBus(), ctx=_ctx(allowed=True))
    assert not result.is_error
    assert result.content == "done"
    assert t.invoked is True           # 放行 → 真的跑了工具


async def test_denied_emits_no_start_event():
    """权限拒绝【不发】tool.call_started。

    这是 P1-5 的核心:前端(Changes / Tasks / Skills 面板)是拿 start 事件记账的,
    只要 start 抢在审批之前发出去,拒绝掉的写入就会留在面板上,而文件根本没动。
    """
    r = ToolRegistry()
    r.register(DummyTool("write_file"))
    bus = EventBus()
    seen = _recorder(bus)

    await invoke_tool(registry=r, tool_call=ToolCallBlock("1", "write_file", {"path": "a.txt"}),
                      bus=bus, ctx=_ctx(allowed=False))

    types = [e.type for e in seen]
    assert types == ["tool.call_finished"]          # 只有收尾,没有开始
    finished = seen[0]
    # 没有 start 事件配对了,finish 必须自带名字和参数,前端才画得出这一行
    assert finished.tool_name == "write_file"
    assert finished.params == {"path": "a.txt"}
    assert finished.is_error is True


async def test_allowed_emits_start_then_finish():
    r = ToolRegistry()
    r.register(DummyTool("write_file"))
    bus = EventBus()
    seen = _recorder(bus)

    await invoke_tool(registry=r, tool_call=ToolCallBlock("1", "write_file", {"path": "a.txt"}),
                      bus=bus, ctx=_ctx(allowed=True))

    assert [e.type for e in seen] == ["tool.call_started", "tool.call_finished"]


async def test_unknown_tool_emits_no_start_event():
    bus = EventBus()
    seen = _recorder(bus)
    await invoke_tool(registry=ToolRegistry(), tool_call=ToolCallBlock("1", "nope", {}),
                      bus=bus, ctx=_ctx())
    assert [e.type for e in seen] == ["tool.call_finished"]
    assert seen[0].tool_name == "nope"
