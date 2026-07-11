from typing import Protocol

from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.llm.types import LlmResponse


class LLMProvider(Protocol):
    async def chat(self,messages,tool_schemas,bus: EventBus, run_id: str) -> LlmResponse: ...
