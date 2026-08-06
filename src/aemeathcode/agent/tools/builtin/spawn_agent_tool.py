import uuid

from aemeathcode.agent.tools.base import BaseTool, ToolResult
from aemeathcode.agent.events.bus import EventBus
from aemeathcode.core.context import ExecutionContext
from aemeathcode.core.task.manager import TaskManager
from aemeathcode.transport.ipc_broadcaster import Subscriber

def _final_text(messages: list[dict]) -> str:
    """从后往前找最近一条 assistant 消息,抽出纯文本当子 agent 的结论。

    content 可能是 str,也可能是块列表 [{"type":"text","text":...}, ...];
    从后往前扫是为了兜"success 但最后一条恰好是 tool_result"的边角。
    """
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text = "\n".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
            if text.strip():
                return text
    return ""


class SpawnAgentTool(BaseTool):
    name = 'spawn_agent'
    description = '生成一个子agent独立完成一个子任务，只返回结论'
    input_schema = {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "派给子agent的子任务目标"
            }
        },
        "required": ["goal"]
    }
    safety_timeout = None

    async def invoke(self,params,ctx)->ToolResult:
        from aemeathcode.agent.loop import Agent
        from aemeathcode.agent.tools import registry
        try:
            sub_goal = params.get("goal")
            sub_run_id = str(uuid.uuid4())
            sub_bus = EventBus()
            sub_bus.subscribe(ctx.services.broadcaster.handle)

            # 状态各建(新 run_id/messages/tasks)、服务借父(services=ctx.services 整包共享)
            sub_ctx = ExecutionContext(goal=sub_goal,max_steps=ctx.max_steps,run_id=sub_run_id,messages=[],tasks=TaskManager(),services=ctx.services)
            # 防递归:子 agent 拿"全部工具减 spawn_agent"的派生 registry,连 schema 都看不到自己,自然无法再 spawn
            child_registry = registry.subset([n for n in registry.names() if n != self.name])

            sub_agent = Agent(ctx=sub_ctx,provider=ctx.services.provider, registry=child_registry, bus=sub_bus,compactor=ctx.services.compactor)

            sub_subscriber = Subscriber(writer=ctx.services.writer, scope=f"run:{sub_run_id}", topics=["*"])
            ctx.services.broadcaster.subscribe(sub_subscriber)
            try:
                await sub_agent.loop()
            finally:
                ctx.services.broadcaster.unsubscribe_with_subscriber(sub_subscriber=sub_subscriber)

            if sub_ctx.status == "success":
                result = _final_text(sub_ctx.messages) or "子任务完成，但无文本输出"
                return ToolResult(content=result, is_error=False)
            else:
                return ToolResult(content=f"子 agent 失败：{sub_ctx.reason}",
                                  is_error=True, error_type="subagent_failed")

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )