import asyncio
import json
from asyncio import StreamReader, StreamWriter

# MCP stdio 传输 = 换行分隔 JSON(NDJSON):一条消息一行、\n 结尾,消息内不含裸换行。
# (不是 LSP 的 Content-Length——那是记混了。这里就是 socket_client 那套 readline + json。)


async def read_frame(reader: StreamReader) -> dict:
    line = await reader.readline()
    if not line:                                      # 空字节 = EOF,对端关了
        raise asyncio.IncompleteReadError(b"", None)  # 复用这个异常,serve/reader_loop 的 except 不用改
    return json.loads(line)


async def write_frame(writer: StreamWriter, obj: dict):
    writer.write(json.dumps(obj).encode() + b"\n")
    await writer.drain()
