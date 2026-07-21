
from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import RunStartedEvent, RunFinishedEvent
from aemeathcode.agent.llm.base import LLMProvider
from aemeathcode.agent.tools import ToolRegistry
from aemeathcode.agent.tools.invocation import invoke_tool
from aemeathcode.core.context import ExecutionContext

class Agent:
    def __init__(self,
                 ctx: ExecutionContext,
                 provider: LLMProvider,
                 registry: ToolRegistry,
                 bus: EventBus):
        self.provider = provider
        self.registry = registry
        self.bus = bus
        self.ctx = ctx

    async def loop(self) -> None:
        await self.bus.publish(RunStartedEvent(goal=self.ctx.goal, run_id=self.ctx.run_id))

        while True:
            if self.ctx.max_steps <= 0:
                await self.bus.publish(RunFinishedEvent(status="error", run_id=self.ctx.run_id, steps=self.ctx.step,content="达到最大轮数",
                                                        input_tokens=self.ctx.total_input_tokens,output_tokens=self.ctx.total_output_tokens,cache_read=self.ctx.total_cache_read))
                return None

            self.ctx.step+=1
            resp = await self.provider.chat(messages=self.ctx.messages,
                                            tool_schemas=self.registry.tool_schemas(),
                                            bus=self.bus,
                                            run_id=self.ctx.run_id)

            self.ctx.token_add(resp)

            if resp.stop_reason == "end_turn":
                await self.bus.publish(RunFinishedEvent(status="success",run_id=self.ctx.run_id,steps=self.ctx.step,content=resp.text if resp.text is not None else "(模型未返回文本)",
                                                        input_tokens=self.ctx.total_input_tokens,output_tokens=self.ctx.total_output_tokens,cache_read=self.ctx.total_cache_read))
                self.ctx.mark_success()
                return None
            elif resp.stop_reason == "tool_use":

                blocks = []
                if resp.text:
                    blocks.append({"type": "text", "text": resp.text})
                for tc in resp.tool_calls:
                    blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})

                self.ctx.add_assistant_message(content=blocks)

                tool_results = []
                for tc in resp.tool_calls:
                    result = await invoke_tool(registry=self.registry,tool_call=tc,bus=self.bus,run_id=self.ctx.run_id)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result.content,  # ToolResult 的 .content
                    })
                self.ctx.add_tool_results(tool_result=tool_results)

            elif resp.stop_reason == "max_tokens":
                await self.bus.publish(RunFinishedEvent(status="error", run_id=self.ctx.run_id, steps=self.ctx.step,
                                                    content="回复太长被截断",input_tokens=self.ctx.total_input_tokens,output_tokens=self.ctx.total_output_tokens,cache_read=self.ctx.total_cache_read))
                self.ctx.mark_failed("回复太长被截断")
                return None

            elif resp.stop_reason == "refusal":
                await self.bus.publish(RunFinishedEvent(status="error", run_id=self.ctx.run_id, steps=self.ctx.step,
                                                    content="拒答",input_tokens=self.ctx.total_input_tokens,output_tokens=self.ctx.total_output_tokens,cache_read=self.ctx.total_cache_read))
                self.ctx.mark_failed("拒答")
                return None
            else:
                await self.bus.publish(RunFinishedEvent(status="error", run_id=self.ctx.run_id, steps=self.ctx.step,
                                                        content="未知错误",input_tokens=self.ctx.total_input_tokens,output_tokens=self.ctx.total_output_tokens,cache_read=self.ctx.total_cache_read))
                self.ctx.mark_failed("未知错误")
                return None
            self.ctx.max_steps -= 1
