import asyncio, sys
from aemeathcode.core.mcp.framing import read_frame, write_frame

async def stdio_streams():
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=1024*1024)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    w_transport, w_protocol = await loop.connect_write_pipe(
        lambda: asyncio.streams.FlowControlMixin(), sys.stdout)
    writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)
    return reader, writer


async def serve():
    reader, writer = await stdio_streams()
    while True:
        try:
            req = await read_frame(reader)      # 读一个请求
        except asyncio.IncompleteReadError:     # ← EOF:client 关了 stdin,收工
            break
        resp = handle(req)                       # 按 method 处理
        if resp is not None:
            await write_frame(writer, resp)          # 回一个响应

# 这台测试 server 暴露的工具(v4 的 tools/call 也会用这张表)
TOOLS = [
    {
        "name": "add",
        "description": "两数相加",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
]


def handle(req):
    """请求(有 id)→ 套信封回响应;通知(无 id)→ None(不回)。"""
    req_id = req.get("id")
    if req_id is None:
        return None                       # 通知,不回
    result = dispatch(req.get("method"), req.get("params") or {})
    if result is None:                    # 未知方法 → JSON-RPC 错误
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"未知方法:{req.get('method')}"}}
    return {"jsonrpc": "2.0", "id": req_id, "result": result}   # 信封只在这套一次


def dispatch(method, params):
    """按 method 算出 result(不管信封);未知方法返回 None。"""
    if method == "initialize":
        return {"protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-server", "version": "0.1"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params["name"];
        args = params["arguments"]
        if name == "add":
            s = args["a"] + args["b"]
            return {"content": [{"type": "text", "text": str(s)}], "isError": False}
    return None


if __name__ == "__main__":
    asyncio.run(serve())