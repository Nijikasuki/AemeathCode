import asyncio
import sys
import uuid

from aemeathcode.core.mcp.framing import read_frame, write_frame

_REQUEST_TIMEOUT = 60   # 单个请求等响应上限(秒):server 挂死时别让 _send 永久卡住(补参考 Tier1)


class MCPClient:
    def __init__(self,command: list[str]):
        self._command = command
        self._proc = None
        self._pending = {}

    async def start(self):
        self._proc = await asyncio.create_subprocess_exec(*self._command,stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, limit=1024*1024)
        self._reader_task = asyncio.create_task(self.reader_loop())

    async def stop(self):
        if self._proc is None:
            return
        self._proc.stdin.close()
        self._proc.terminate()
        await asyncio.wait_for(self._proc.wait(), timeout=2)

    async def reader_loop(self):
        while True:
            try:
                msg = await read_frame(self._proc.stdout)
            except asyncio.IncompleteReadError:
                break
            req_id = msg.get("id")
            fut = self._pending.pop(req_id, None) if req_id is not None else None
            if fut and not fut.done():
                fut.set_result(msg.get("result"))

    async def _send(self, method: str, params: dict | None = None):
        """请求:建信封(带 id)→ 挂 Future → 发出 → 等响应。返回响应的 result。"""
        req_id = uuid.uuid4().hex
        fut = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        await write_frame(self._proc.stdin, {
            "jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {},
        })
        try:
            return await asyncio.wait_for(fut, timeout=_REQUEST_TIMEOUT)
        finally:
            self._pending.pop(req_id, None)   # 超时/正常都摘掉挂单;晚到的响应 reader loop pop 到 None 自然跳过

    async def _notify(self, method: str, params: dict | None = None):
        """通知:没 id、不挂 Future、不等回应(单向信号)。"""
        await write_frame(self._proc.stdin, {
            "jsonrpc": "2.0", "method": method, "params": params or {},
        })

    async def initialize(self):
        """MCP 握手三步:initialize(请求)→ 等响应 → initialized(通知)。"""
        await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "aemeath", "version": "0.1"},
        })
        await self._notify("notifications/initialized")

    async def list_tools(self) -> list[dict]:
        """握手后发现工具:tools/list → 返回工具定义列表。"""
        result = await self._send("tools/list")
        return result.get("tools", [])

    async def call_tool(self,name,arguments):
        return await self._send("tools/call", {"name": name, "arguments": arguments})

