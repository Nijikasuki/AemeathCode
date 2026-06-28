import asyncio
import json
import logging

from pydantic import ValidationError

from aemeathcode.bus.envelope import make_error, JsonRpcRequest, JsonRpcSuccess

logger = logging.getLogger(__name__)

class SocketServer():
    def __init__(self,host:str,port:int):
        self.host = host
        self.port = port
        self._handlers = {}
        self._server = None

    def register(self,method:str,handler):
        self._handlers[method] = handler

    async def start(self):
        if await self._check_port():
            raise SystemExit(f"core already running at {self.host}:{self.port}")

        self._server = await asyncio.start_server(self._handle_connection,host=self.host,port=self.port,limit=1024*1024)
        return f"{self.host}:{self.port}"

    async def stop(self):
        if self._server is None:
            return
        self._server.close()
        await asyncio.wait_for(self._server.wait_closed(), timeout=2)

    async def _handle_connection(self,reader, writer):
        try:
            while True:
                try:
                    line = await reader.readline()
                except  (asyncio.LimitOverrunError, ValueError):
                    response = make_error(None, -32600, "Request too large")
                    await self._send(response, writer)
                    return

                if not line:
                    break
                await self._handle_line(line, writer)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_line(self,msg, writer):
        try:
            msg_dict = json.loads(msg)
        except json.decoder.JSONDecodeError:
            response = make_error(None, -32700, "Parse Error")
            await self._send(response, writer)
            return
        try:
            req = JsonRpcRequest.model_validate(msg_dict)
        except ValidationError:
            response = make_error(None, -32600, "Invalid Request")
            await self._send(response, writer)
            return

        handler = self._handlers.get(req.method)
        if handler is None:
            response = make_error(req.id, -32601, "Method not found")
            await self._send(response, writer)
            return
        try:
            result = await handler(req.params)
        except Exception as e:
            logger.exception("handler %s crashed",req.method)
            response = make_error(req.id, -32603, "Internal error")
            await self._send(response, writer)
            return

        response = JsonRpcSuccess(id=req.id, result=result)
        await self._send(response, writer)


    async def _send(self,response, writer):
        writer.write(response.model_dump_json().encode() + b"\n")
        await writer.drain()

    async def _check_port(self):
        try:
            reader, writer = await asyncio.open_connection(self.host, self.port)
            logger.debug("端口有服务在监听")
            writer.close()
            await writer.wait_closed()
            return True
        except ConnectionRefusedError:
            logger.debug("端口没有监听（被拒绝连接）")
            return False
        except Exception as e:
            logger.debug("其他错误: %s", e)
            return False