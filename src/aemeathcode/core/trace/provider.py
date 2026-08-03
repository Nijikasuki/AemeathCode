import time
from datetime import datetime
from typing import Literal
from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.llm.base import LLMProvider
from aemeathcode.agent.llm.types import LlmResponse
from aemeathcode.core.trace.record import TraceRecord
from aemeathcode.core.trace.writer import TraceWriter


class TracingProvider(LLMProvider):
    def __init__(self,inner:LLMProvider,trace:TraceWriter) -> None:
        self._inner = inner
        self._trace = trace
        self.model = inner.model

    async def chat(self, messages, tool_schemas, bus: EventBus, run_id: str) -> LlmResponse:
        start = time.monotonic()
        ts_start = datetime.now().isoformat()
        status: Literal["ok", "error"] = "ok"
        error: str | None = None
        try:
            return await self._inner.chat(messages, tool_schemas, bus, run_id)
        except Exception as e:
            status = "error"
            error = str(e)
            raise
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            record = TraceRecord(run_id=run_id,
                                 category="llm",
                                 name=self._inner.model,
                                 ts= ts_start,
                                 duration_ms=duration_ms,
                                 status=status,
                                 error=error)
            self._trace.emit(record)

    async def complete(self, system: str, messages: list) -> str:
        # 透明转发(先不计时);辅助调用不走 bus/事件,tracing 以后想加再加。
        return await self._inner.complete(system, messages)


