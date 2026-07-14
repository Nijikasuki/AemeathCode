import asyncio
import json
import uuid
from typing import Any

from aemeathcode.bus.envelope import JsonRpcRequest

class IpcError(Exception):
    def __init__(self, code:int, message:str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class SocketClient:
    def __init__(self, host:str, port:int):
        self.host,self.port = host,port
        self._reader = None
        self._writer = None
        self._event_handlers = []
        self._pending = {}

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, limit=1024 * 1024
        )

    def on_event(self, handler):
        self._event_handlers.append(handler)

    async def send_command(self,method,params)-> Any:
        req_id = uuid.uuid4().hex
        fut = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        self._writer.write(JsonRpcRequest(id=req_id,method=method,params=params).model_dump_json().encode() + b'\n')
        await self._writer.drain()
        return await fut


    async def run_event_loop(self):
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                await self._dispatch(line)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("连接已断开"))
            self._pending.clear()

    async def close(self):
        self._writer.close()
        await self._writer.wait_closed()

    async def _dispatch(self,line):
        msg = json.loads(line)
        if msg.get("kind") == "event":
            event = msg["event"]
            for handler in self._event_handlers:
                await handler(event)
        elif "jsonrpc" in msg:
            req_id = msg["id"]
            fut = self._pending.pop(req_id,None)
            if fut and not fut.done():
                if "error" in msg:
                    fut.set_exception(IpcError(msg["error"]["code"],msg["error"]["message"]))
                else:
                    fut.set_result(msg.get("result"))



