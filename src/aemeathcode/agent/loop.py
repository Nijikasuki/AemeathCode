import uuid

from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import RunStartedEvent, RunFinishedEvent
from aemeathcode.agent.llm.base import LLMProvider
from aemeathcode.agent.tools import ToolRegistry
from aemeathcode.agent.tools.invocation import invoke_tool
from aemeathcode.core.config import get_config

class Agent:
    def __init__(self,
                 provider: LLMProvider,
                 registry: ToolRegistry,
                 bus: EventBus,
                 goal:str):
        config = get_config()
        self.provider = provider
        self.registry = registry
        self.bus = bus
        self.max_steps = config.max_steps
        self.goal = goal
        self.messages =  [{"role": "user","content": goal}]
        self.run_id = str(uuid.uuid4())

    async def loop(self) -> None:
        await self.bus.publish(RunStartedEvent(goal=self.goal, run_id=self.run_id))
        round_no = 0
        while True:
            if self.max_steps <= 0:
                await self.bus.publish(RunFinishedEvent(status="error", run_id=self.run_id, steps=round_no,
                                                        content="达到最大轮数"))
                return None

            round_no += 1
            resp = await self.provider.chat(messages=self.messages,
                                            tool_schemas=self.registry.tool_schemas(),
                                            bus=self.bus,
                                            run_id=self.run_id)

            if resp.stop_reason == "end_turn":
                await self.bus.publish(RunFinishedEvent(status="success",run_id=self.run_id,steps=round_no,content=resp.text if resp.text is not None else "(模型未返回文本)"))
                return None
            elif resp.stop_reason == "tool_use":

                blocks = []
                if resp.text:
                    blocks.append({"type": "text", "text": resp.text})
                for tc in resp.tool_calls:
                    blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})

                self.messages.append({"role":"assistant","content":blocks})

                tool_results = []
                for tc in resp.tool_calls:
                    result = await invoke_tool(registry=self.registry,tool_call=tc,bus=self.bus,run_id=self.run_id)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result.content,  # ToolResult 的 .content
                    })
                self.messages.append({"role": "user", "content": tool_results})

            elif resp.stop_reason == "max_tokens":
                await self.bus.publish(RunFinishedEvent(status="error", run_id=self.run_id, steps=round_no,
                                                    content="回复太长被截断"))
                return None

            elif resp.stop_reason == "refusal":
                await self.bus.publish(RunFinishedEvent(status="error", run_id=self.run_id, steps=round_no,
                                                    content="拒答"))
                return None
            else:
                await self.bus.publish(RunFinishedEvent(status="error", run_id=self.run_id, steps=round_no,
                                                        content="未知错误"))
                return None
            self.max_steps -= 1
