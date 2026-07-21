from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import ThinkingEvent,LlmTokenEvent
from aemeathcode.agent.llm.base import LLMProvider
from aemeathcode.agent.llm.types import LlmResponse, UsageStats, ToolCallBlock
from anthropic import AsyncAnthropic

from aemeathcode.agent.prompts import SYSTEM_PROMPT


class AnthropicProvider(LLMProvider):
    def __init__(self,model:str):
        self._client = AsyncAnthropic()
        self.model = model

    async def chat(self,
                   messages: list[dict[str, object]],
                   tool_schemas: list[dict[str, object]],
                   bus: EventBus,
                   run_id: str) -> LlmResponse:
        
        async with self._client.messages.stream(system=[{
                                                        "type": "text",
                                                        "text": SYSTEM_PROMPT,
                                                        "cache_control": {"type": "ephemeral"},}],
                                                model=self.model,
                                                max_tokens=1024,
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
            text = next((b.text for b in final.content if b.type == "text"), ""),
            usage = UsageStats(input_tokens=final.usage.input_tokens,
                               output_tokens=final.usage.output_tokens,
                               cache_creation_input_tokens=final.usage.cache_creation_input_tokens,
                               cache_read_input_tokens=final.usage.cache_read_input_tokens),
        )


