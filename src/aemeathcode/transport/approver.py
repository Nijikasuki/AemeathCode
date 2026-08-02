import uuid
import asyncio
from aemeathcode.bus.envelope import AskEnvelope


class Approver:
    def __init__(self,writer,registry):
        self._writer = writer
        self._registry = registry

    async def ask(self,tool_name:str,detail:str,run_id:str):
        approval_id = uuid.uuid4().hex
        fut = self._registry.register(approval_id,self._writer)
        try:
            self._writer.write(AskEnvelope(approval_id=approval_id,tool_name=tool_name,detail=detail,run_id=run_id).model_dump_json().encode() + b'\n')
            await self._writer.drain()
            return await asyncio.wait_for(fut, timeout=600)
        except (TimeoutError, ConnectionError, OSError):
            return "deny"
        finally:
            self._registry.discard(approval_id)

