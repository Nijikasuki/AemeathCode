import asyncio
import time
from datetime import datetime
from typing import Literal

from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import ToolCallStartEvent, ToolCallFinishedEvent
from aemeathcode.agent.llm.types import ToolCallBlock
from aemeathcode.agent.tools import ToolRegistry
from aemeathcode.agent.tools.base import ToolResult
from aemeathcode.core.context import ExecutionContext
from aemeathcode.core.trace.record import TraceRecord


async def invoke_tool(registry : ToolRegistry,
                      tool_call : ToolCallBlock,
                      bus : EventBus,
                      ctx:ExecutionContext) -> ToolResult:

    await bus.publish(ToolCallStartEvent(tool_use_id = tool_call.id,tool_name=tool_call.name,params=tool_call.input,run_id=ctx.run_id))
    tool = registry.get(tool_call.name)
    # 调用前先查 schema 里 required 的参数缺没缺,缺了直接返回、不进 invoke(tool 为 None 时给空列表)
    missing = [p for p in tool.input_schema.get("required", []) if p not in tool_call.input] if tool else []

    if tool is None:
        result = ToolResult(content=f"未知工具:{tool_call.name}",is_error=True,error_type="unknown_tool")
    elif missing:
        result = ToolResult(content=f"缺少必需参数: {', '.join(missing)}",is_error=True,error_type="schema_error")
    else:
        perm = await ctx.services.permission_manager.check(tool=tool,params=tool_call.input,approver=ctx.services.approver,run_id=ctx.run_id)
        if not perm.allowed:
            result = ToolResult(content=f"权限被拒绝:{perm.reason}",is_error=True, error_type="permission_denied")
        else:
            start = time.monotonic()
            ts_start = datetime.now().isoformat()
            status: Literal["ok", "error"] = "ok"
            error: str | None = None
            try:
                if tool.safety_timeout is not None:
                    result = await asyncio.wait_for(tool.invoke(params=tool_call.input,ctx=ctx), timeout=tool.safety_timeout)
                else:
                    result = await tool.invoke(params=tool_call.input,ctx=ctx)
            except asyncio.TimeoutError:
                result = ToolResult(content="超时",is_error=True,error_type="timeout")
                error = "timeout"
                status = "error"
            except Exception as e:
                result = ToolResult(content=f"运行出错{e}", is_error=True, error_type="runtime_error")
                error = f"运行出错{e}"
                status = "error"
            finally:
                if ctx.services.trace is not None:
                    duration_ms = (time.monotonic() - start) * 1000
                    record = TraceRecord(run_id=ctx.run_id,
                                         category="tool",
                                         name=tool_call.name,
                                         ts=ts_start,
                                         duration_ms=duration_ms,
                                         status=status,
                                         error=error)
                    ctx.services.trace.emit(record)
    await bus.publish(ToolCallFinishedEvent(tool_use_id=tool_call.id,is_error=result.is_error,content=result.content,run_id=ctx.run_id))
    return result