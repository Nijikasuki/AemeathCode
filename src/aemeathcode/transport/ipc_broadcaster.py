from asyncio import StreamWriter
from dataclasses import dataclass
import fnmatch

from aemeathcode.bus.envelope import EventEnvelope

@dataclass
class Subscriber:
    writer: StreamWriter
    scope: str
    topics: list[str]

class IpcEventBroadcaster:
    def __init__(self):
        self._subscribers = []

    def subscribe(self, subscriber:Subscriber):
        self._subscribers.append(subscriber)

    def unsubscribe(self, writer:StreamWriter):
        for subscriber in self._subscribers:
            if subscriber.writer is writer:
                self._subscribers.remove(subscriber)
                break

    @staticmethod
    def _match(run_id, scope) -> bool:
        if scope == "global":
            return True
        if scope.startswith("run:"):
            return scope[4:] == run_id  # 抠出 "run:" 后面的 id,精确比
        return False

    @staticmethod
    def _match_topic(event_type:str,topics:list[str]) -> bool:
        return any(fnmatch.fnmatch(event_type, p) for p in topics)

    async def handle(self,event):
        data = EventEnvelope(event=event.model_dump()).model_dump_json().encode() + b"\n"
        run_id = event.run_id
        dead = []
        for subscriber in list(self._subscribers):
            if not self._match(run_id=run_id, scope=subscriber.scope):  continue# ← 不匹配就跳过
            if not self._match_topic(event_type=event.type,topics=subscriber.topics): continue
            try:
                subscriber.writer.write(data)
                await subscriber.writer.drain()
            except (ConnectionResetError, BrokenPipeError,OSError):
                dead.append(subscriber.writer)
        for writer in dead:
            self.unsubscribe(writer)