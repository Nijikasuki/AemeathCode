"""framing 的单元测试:read_frame / write_frame(MCP 的 NDJSON,一条消息一行)。

第一次看测试的话,记住三段式 **AAA**:
  Arrange 准备输入 → Act 调用被测代码 → Assert 断言结果符合预期。
`assert <条件>` 为 False 时,pytest 就把这个测试标红(FAILED),并告诉你哪行、期望 vs 实际。
函数名必须以 test_ 开头,pytest 才会当测试收集。
"""
import asyncio
import pytest

from aemeathcode.core.mcp.framing import read_frame, write_frame


class FakeWriter:
    """假的 StreamWriter。write_frame 只用到 .write() 和 .drain(),所以造个最小替身:
    把写入的字节攒进 buf,drain 空转。这样测试不用开真的网络/子进程,又快又稳。"""

    def __init__(self):
        self.buf = bytearray()

    def write(self, data: bytes):
        self.buf.extend(data)

    async def drain(self):
        pass


async def test_framing_roundtrip():
    """写一个 dict、再读回来,应该一模一样(round-trip 无损)——一次覆盖两个函数。"""
    # Arrange:准备一个要发的 dict
    obj = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

    # Act:① write_frame 把它写成帧(字节攒进 FakeWriter)
    writer = FakeWriter()
    await write_frame(writer, obj)
    #      ② 把那些字节喂给 StreamReader,再 read_frame 读回来
    reader = asyncio.StreamReader()
    reader.feed_data(bytes(writer.buf))
    reader.feed_eof()
    result = await read_frame(reader)

    # Assert:读回来的应和写进去的完全相等
    assert result == obj

async def test_read_frame_eof():
    # Arrange:一个【立刻 EOF、没有数据】的 reader
    reader = asyncio.StreamReader()
    reader.feed_eof()
    # Act + Assert:read_frame 应该抛 IncompleteReadError
    with pytest.raises(asyncio.IncompleteReadError):
        await read_frame(reader)
    # 如果 read_frame 【没】抛这个异常,这个测试就 FAILED


async def test_write_frame_is_ndjson():
    """write_frame 的字节契约:就是 JSON + 一个换行(NDJSON),【没有】 Content-Length 头。
    钉死这个格式,以后谁手滑改回 Content-Length,这条会立刻红。"""
    writer = FakeWriter()
    await write_frame(writer, {"a": 1})
    assert bytes(writer.buf) == b'{"a": 1}\n'


async def test_roundtrip_multibyte():
    """中文(多字节)也要无损 round-trip:防"长度按字符数而非字节数"那类坑。"""
    obj = {"msg": "你好世界"}
    writer = FakeWriter()
    await write_frame(writer, obj)
    reader = asyncio.StreamReader()
    reader.feed_data(bytes(writer.buf))
    reader.feed_eof()
    assert await read_frame(reader) == obj