from asyncio import StreamWriter

from pydantic import BaseModel

from aemeathcode.bus.envelope import EventEnvelope


class IpcBroadcaster:
    def __init__(self, writer:StreamWriter):
        self.writer = writer
    async def broadcast(self, event:BaseModel):
        run_event = EventEnvelope(event=event.model_dump())
        self.writer.write(run_event.model_dump_json().encode() + b"\n")
        await self.writer.drain()
