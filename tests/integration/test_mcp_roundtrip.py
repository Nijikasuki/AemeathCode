"""MCP 集成测试:真拉起测试 server 子进程,走完整栈——分帧 + 握手 + 发现 + 调用。

【新概念:集成测试】
前面的单测都在【进程内】测单个函数/类(快、隔离)。这个不同:它 create_subprocess 拉起
真的 test server,验证 client 和 server 【端到端】能对话。慢一点,但覆盖"各部件拼一起还对不对"。

【新概念:try/finally 清理】
不管断言过不过,finally 里 stop() 都要跑,把子进程收掉——测试不能留下僵尸进程。
"""
import sys

from aemeathcode.core.mcp.client import MCPClient


async def test_mcp_client_server_roundtrip():
    client = MCPClient([sys.executable, "-m", "aemeathcode.core.mcp.server"])
    await client.start()
    try:
        await client.initialize()                        # 三步握手
        tools = await client.list_tools()                # 发现工具
        assert any(t["name"] == "add" for t in tools)    # test server 暴露了 add

        result = await client.call_tool("add", {"a": 2, "b": 3})   # 真调一次
        assert result["content"][0]["text"] == "5"       # 2+3=5
        assert result["isError"] is False
    finally:
        await client.stop()                              # 无论如何收掉子进程
