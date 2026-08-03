from typing import Protocol

from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.llm.types import LlmResponse


class LLMProvider(Protocol):
    model:str
    async def chat(self,messages,tool_schemas,bus: EventBus, run_id: str) -> LlmResponse: ...
    # 主循环外的辅助调用(概括 / 生成标题…):纯 system + messages → 文本,
    # 不带工具、不注入便签、不流事件、不走 bus。
    async def complete(self, system: str, messages: list) -> str: ...
