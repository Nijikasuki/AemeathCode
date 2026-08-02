import asyncio

from asyncio import StreamWriter
from dataclasses import dataclass

@dataclass
class Pending:
    future: asyncio.Future
    writer: StreamWriter


class ApprovalRegistry:
    def __init__(self):
        self._pending = {}

    def register(self,approval_id:str,writer:StreamWriter):
        fut = asyncio.get_running_loop().create_future()
        pending = Pending(fut,writer)
        self._pending[approval_id] = pending
        return fut

    def resolve(self, approval_id:str,decision):
        pending = self._pending.pop(approval_id, None)
        if pending is None:
            return
        if not pending.future.done():
            pending.future.set_result(decision)

    def fail_writer(self,writer:StreamWriter):
        for approval_id,pending in list(self._pending.items()):
            if not pending.future.done() and pending.writer == writer:
                pending.future.set_exception(ConnectionError("连接已断开"))
                self._pending.pop(approval_id, None)

    def discard(self,approval_id:str):
        self._pending.pop(approval_id, None)