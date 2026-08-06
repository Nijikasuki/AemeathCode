from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import ThinkingEvent,LlmTokenEvent
from aemeathcode.agent.llm.base import LLMProvider
from aemeathcode.agent.llm.models import output_budget
from aemeathcode.agent.llm.types import LlmResponse, UsageStats, ToolCallBlock
from anthropic import AsyncAnthropic

from aemeathcode.agent.prompts import SYSTEM_PROMPT
from aemeathcode.core.memory.note import NoteStore


class AnthropicProvider(LLMProvider):
    def __init__(self,model:str,note_store:NoteStore,project_memory:str="",system_prompt:str=SYSTEM_PROMPT) -> None:
        self._client = AsyncAnthropic()
        self.model = model
        self._note_store = note_store
        self._project_memory = project_memory
        self._system_prompt = system_prompt   # 默认主 agent prompt;子 agent 按 profile 传角色 prompt

    async def chat(self,
                   messages: list[dict[str, object]],
                   tool_schemas: list[dict[str, object]],
                   bus: EventBus,
                   run_id: str) -> LlmResponse:
        notes = self._note_store.load()
        system = [{"type": "text","text": self._system_prompt,"cache_control": {"type": "ephemeral"},}]
        if self._project_memory:
            system.append({"type": "text","text": "# 项目记忆(AEMEATH.md)\n" + self._project_memory})
        if notes:
            system.append({"type": "text","text": "# 已记录的便签\n" + "\n".join(f"- {n}" for n in notes)})

        async with self._client.messages.stream(system=system,
                                                model=self.model,
                                                max_tokens=output_budget(self.model),
                                                tools=tool_schemas,
                                                messages=messages) as stream:
            async for event in stream:
                if event.type == "text":
                    await bus.publish(LlmTokenEvent(content=event.text,run_id=run_id))
                if event.type == "thinking":
                    await bus.publish(ThinkingEvent(content=event.thinking, run_id=run_id))
            final = await stream.get_final_message()

        return LlmResponse(
            stop_reason= final.stop_reason,
            tool_calls = [ToolCallBlock(b.id,b.name,b.input) for b in final.content if b.type=="tool_use"],
            text = "".join(b.text for b in final.content if b.type == "text"),
            usage = UsageStats(input_tokens=final.usage.input_tokens,
                               output_tokens=final.usage.output_tokens,
                               cache_creation_input_tokens=final.usage.cache_creation_input_tokens,
                               cache_read_input_tokens=final.usage.cache_read_input_tokens),
        )

    async def complete(self, system: str, messages: list) -> str:
        # 辅助调用的干净最小通道:非流式、无工具、不注入便签、不发 bus 事件。
        resp = await self._client.messages.create(system=system,
                                                  model=self.model,
                                                  max_tokens=output_budget(self.model),
                                                  messages=messages)
        return "".join(b.text for b in resp.content if b.type == "text")


