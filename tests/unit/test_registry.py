"""ToolRegistry 的单元测试:register/get/names + subset(防递归靠它)。

这些是纯同步函数,不用 async。注意:测试里用一个最小 DummyTool 当替身,
不牵扯真工具的逻辑——我们只测 registry 本身。
"""
from aemeathcode.agent.tools.base import BaseTool, ToolResult
from aemeathcode.agent.tools.registry import ToolRegistry


class DummyTool(BaseTool):
    """最小工具替身:只有 registry 用到的 name;invoke 随便返回。"""

    def __init__(self, name: str):
        self.name = name
        self.description = "dummy"
        self.input_schema = {"type": "object"}

    async def invoke(self, params, ctx):
        return ToolResult(content="ok")


def test_register_and_get():
    r = ToolRegistry()
    t = DummyTool("foo")
    r.register(t)
    assert r.get("foo") is t        # 存进去、原样取回(is:同一个对象)
    assert r.get("nope") is None    # 没有的返回 None


def test_names():
    r = ToolRegistry()
    r.register(DummyTool("a"))
    r.register(DummyTool("b"))
    assert set(r.names()) == {"a", "b"}


def test_subset_isolates_and_shares():
    """subset 是防递归的核心:返回【新】registry、只留白名单、共享 tool 对象、不动原 registry。"""
    r = ToolRegistry()
    a, b, c = DummyTool("a"), DummyTool("b"), DummyTool("c")
    for t in (a, b, c):
        r.register(t)

    sub = r.subset(["a", "b"])                 # 只要 a、b(模拟"全部减 spawn")
    assert set(sub.names()) == {"a", "b"}      # 只保留白名单
    assert sub is not r                        # 是新对象,不是原 registry
    assert sub.get("a") is a                   # 但共享【同一个】tool 单例
    assert set(r.names()) == {"a", "b", "c"}   # 原 registry 一根没少(没被误伤)


def test_subset_skips_unknown_names():
    """白名单里写了不存在的名字,静默跳过、不抛(subset 的容错)。"""
    r = ToolRegistry()
    r.register(DummyTool("a"))
    assert set(r.subset(["a", "does_not_exist"]).names()) == {"a"}
