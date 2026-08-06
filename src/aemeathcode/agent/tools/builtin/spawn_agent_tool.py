import uuid

from aemeathcode.agent.tools.base import BaseTool, ToolResult
from aemeathcode.agent.events.bus import EventBus
from aemeathcode.core.context import ExecutionContext
from aemeathcode.core.task.manager import TaskManager
from aemeathcode.transport.ipc_broadcaster import Subscriber
from aemeathcode.agent.events.models import SubAgentStartedEvent

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
    description = ('生成一个子 agent 独立完成一个子任务,只返回结论。'
                  '派活时【尽量指定 agent 角色】以获得更专注/更安全的执行:'
                  "审阅或找问题用 agent='reviewer'、拆解规划用 'planner'、动手执行用 'executor';"
                  '实在不匹配任何角色再省略(走通用子 agent)。')
    input_schema = {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "派给子agent的子任务目标"
            },
            "agent": {
                "type": "string",
                "enum": ["reviewer", "planner", "executor"],
                "description": "子agent以哪个角色跑:reviewer(审阅/挑问题,只读工具) / planner(拆解规划) / executor(动手执行)。按子任务性质选;不填=通用子agent"
            }
        },
        "required": ["goal"]
    }
    safety_timeout = None

    async def invoke(self,params,ctx)->ToolResult:
        from aemeathcode.agent.loop import Agent
        from aemeathcode.agent.tools import registry
        try:
            parent_tool_use_id = ctx.current_tool_use_id
            sub_goal = params.get("goal")
            sub_run_id = str(uuid.uuid4())
            sub_bus = EventBus()
            sub_bus.subscribe(ctx.services.broadcaster.handle)

            # 状态各建(新 run_id/messages/tasks)、服务借父(services=ctx.services 整包共享)
            sub_ctx = ExecutionContext(goal=sub_goal,max_steps=ctx.max_steps,run_id=sub_run_id,messages=[],tasks=TaskManager(),services=ctx.services)
            # profile(角色):给了就按角色造【专属 provider】(自己的 system_prompt + 模型),否则借父的
            agent_name = params.get("agent")
            profile = ctx.services.profile_store.get(agent_name) if agent_name else None
            if profile is not None:
                from aemeathcode.agent.llm.provider import AnthropicProvider
                from aemeathcode.core.trace.provider import TracingProvider
                from aemeathcode.core.memory.loader import load_project_memory
                from aemeathcode.core.config import get_data_dir
                sub_provider = TracingProvider(
                    inner=AnthropicProvider(model=profile.model or ctx.services.provider.model,
                                            note_store=ctx.services.note_store,
                                            project_memory=load_project_memory(get_data_dir()),
                                            system_prompt=profile.system_prompt),
                    trace=ctx.services.trace)
            else:
                sub_provider = ctx.services.provider

            # 工具集:profile 指定的白名单,否则全部;两种都【强制去掉 spawn 自己】防递归
            allowed = profile.tools if (profile and profile.tools is not None) else registry.names()
            child_registry = registry.subset([n for n in allowed if n != self.name])

            sub_agent = Agent(ctx=sub_ctx,provider=sub_provider, registry=child_registry, bus=sub_bus,compactor=ctx.services.compactor)

            sub_subscriber = Subscriber(writer=ctx.services.writer, scope=f"run:{sub_run_id}", topics=["*"])
            ctx.services.broadcaster.subscribe(sub_subscriber)
            await sub_bus.publish(SubAgentStartedEvent(parent_tool_use_id=parent_tool_use_id, run_id=sub_run_id))
            try:
                await sub_agent.loop()
            finally:
                ctx.services.broadcaster.unsubscribe_with_subscriber(sub_subscriber)

            # 把子 agent 的 token 消耗折回父 ctx(否则子的 LLM 开销凭空蒸发,父 run 和会话都少算)
            ctx.total_input_tokens += sub_ctx.total_input_tokens
            ctx.total_output_tokens += sub_ctx.total_output_tokens
            ctx.total_cache_read += sub_ctx.total_cache_read

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