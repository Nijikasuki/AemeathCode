from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import ThinkingEvent
from aemeathcode.agent.llm.base import LLMProvider
from aemeathcode.agent.llm.types import LlmResponse, UsageStats, ToolCallBlock
from anthropic import AsyncAnthropic

class AnthropicProvider(LLMProvider):
    def __init__(self,model:str):
        self._client = AsyncAnthropic()
        self.model = model

    async def chat(self,
                   messages: list[dict[str, object]],
                   tool_schemas: list[dict[str, object]],
                   bus: EventBus,
                   run_id: str) -> LlmResponse:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            tools=tool_schemas,
            messages=messages
        )
        for b in response.content:
            if b.type == "thinking":
                await bus.publish(ThinkingEvent(content=b.thinking,run_id=run_id))

        return LlmResponse(
            stop_reason= response.stop_reason,
            tool_calls = [ToolCallBlock(b.id,b.name,b.input) for b in response.content if b.type=="tool_use"],
            text = next((b.text for b in response.content if b.type == "text"), ""),
            usage = UsageStats(input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens),
        )


