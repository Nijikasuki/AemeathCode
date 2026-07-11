import asyncio

from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import ToolCallStartEvent, ToolCallFinishedEvent
from aemeathcode.agent.llm.types import ToolCallBlock
from aemeathcode.agent.tools import ToolRegistry
from aemeathcode.agent.tools.base import ToolResult


async def invoke_tool(registry : ToolRegistry,
                      tool_call : ToolCallBlock,
                      bus : EventBus,
                      run_id: str) -> ToolResult:
    await bus.publish(ToolCallStartEvent(tool_use_id = tool_call.id,tool_name=tool_call.name,params=tool_call.input,run_id=run_id))
    tool = registry.get(tool_call.name)
    if tool is None:
        result = ToolResult(content=f"未知工具:{tool_call.name}",is_error=True,error_type="unknown_tool")
    else:
        try:
            result = await asyncio.wait_for(tool.invoke(tool_call.input), timeout=10)
        except asyncio.TimeoutError:
            result = ToolResult(content="超时",is_error=True,error_type="timeout")
        except Exception as e:
            result = ToolResult(content=f"运行出错{e}", is_error=True, error_type="runtime_error")
    await bus.publish(ToolCallFinishedEvent(tool_use_id=tool_call.id,is_error=result.is_error,content=result.content,run_id=run_id))
    return result