"""IpcEventBroadcaster 的单元测试:scope/topics 路由 + 精确退订 + 死连接清理。

用 FakeWriter 抓"发出去的字节"——有字节=匹配上并投递了,没字节=被过滤掉。
"""
from pydantic import BaseModel

from aemeathcode.transport.ipc_broadcaster import IpcEventBroadcaster, Subscriber


class Ev(BaseModel):
    """最小事件:broadcaster 只看 .run_id / .type,并 model_dump 一下。"""
    type: str
    run_id: str


class FakeWriter:
    def __init__(self):
        self.data = bytearray()

    def write(self, b: bytes):
        self.data.extend(b)

    async def drain(self):
        pass


class DeadWriter:
    """一写就抛断连异常,模拟死掉的客户端。"""

    def write(self, b: bytes):
        raise ConnectionResetError("client gone")

    async def drain(self):
        pass


async def test_scope_run_id_match():
    b = IpcEventBroadcaster()
    wa, wb = FakeWriter(), FakeWriter()
    b.subscribe(Subscriber(writer=wa, scope="run:A", topics=["*"]))
    b.subscribe(Subscriber(writer=wb, scope="run:B", topics=["*"]))
    await b.handle(Ev(type="x", run_id="A"))
    assert len(wa.data) > 0     # 订的是 run:A,事件 run_id=A → 收到
    assert len(wb.data) == 0    # 订的是 run:B → 过滤掉


async def test_scope_global_matches_any_run():
    b = IpcEventBroadcaster()
    w = FakeWriter()
    b.subscribe(Subscriber(writer=w, scope="global", topics=["*"]))
    await b.handle(Ev(type="x", run_id="anything"))
    assert len(w.data) > 0      # global 匹配任意 run_id


async def test_topic_glob_filter():
    b = IpcEventBroadcaster()
    w = FakeWriter()
    b.subscribe(Subscriber(writer=w, scope="global", topics=["tool.*"]))
    await b.handle(Ev(type="run.completed", run_id="A"))     # 不匹配 tool.*
    assert len(w.data) == 0
    await b.handle(Ev(type="tool.call_started", run_id="A"))  # 匹配 tool.*
    assert len(w.data) > 0


async def test_unsubscribe_by_object_is_precise():
    """同一 writer 挂两条(run:父 + run:子),按对象删【子】那条,父那条不受影响(坑 A)。"""
    b = IpcEventBroadcaster()
    w = FakeWriter()
    parent = Subscriber(writer=w, scope="run:parent", topics=["*"])
    child = Subscriber(writer=w, scope="run:child", topics=["*"])
    b.subscribe(parent)
    b.subscribe(child)

    b.unsubscribe_with_subscriber(child)          # 只摘子

    await b.handle(Ev(type="x", run_id="parent"))
    assert len(w.data) > 0                         # 父订阅还在
    w.data.clear()
    await b.handle(Ev(type="x", run_id="child"))
    assert len(w.data) == 0                        # 子订阅已被精确删掉


async def test_dead_connection_cleaned_up():
    b = IpcEventBroadcaster()
    b.subscribe(Subscriber(writer=DeadWriter(), scope="global", topics=["*"]))
    await b.handle(Ev(type="x", run_id="A"))       # 写时抛 ConnectionResetError
    assert b._subscribers == []                    # 死连接被惰性清理掉
