"""EventBus 的单元测试:发布送达所有订阅者 + 单个订阅者异常被隔离。

【新概念:测 pub/sub 的"录音机"模式】
回调/发布订阅怎么测?订阅一个"把收到的事件存进列表"的协程(录音机),
publish 之后断言列表 —— 就能验证"谁收到了什么"。
"""
from pydantic import BaseModel

from aemeathcode.agent.events.bus import EventBus


class Ping(BaseModel):
    """测试用的最小事件(publish 只要求是 BaseModel)。"""
    n: int


async def test_publish_delivers_to_all_subscribers():
    bus = EventBus()
    got_a, got_b = [], []

    async def a(e):        # 录音机 A
        got_a.append(e)

    async def b(e):        # 录音机 B
        got_b.append(e)

    bus.subscribe(a)
    bus.subscribe(b)

    event = Ping(n=1)
    await bus.publish(event)

    assert got_a == [event]     # 两个订阅者都收到了同一个事件
    assert got_b == [event]


async def test_subscriber_exception_is_isolated():
    """一个订阅者抛异常,不能连累其它订阅者 —— publish 里 per-subscriber try/except 的保证。"""
    bus = EventBus()
    got = []

    async def boom(e):
        raise RuntimeError("这个订阅者炸了")

    async def ok(e):
        got.append(e)

    bus.subscribe(boom)      # 先注册会炸的
    bus.subscribe(ok)        # 再注册正常的

    await bus.publish(Ping(n=7))   # boom 抛异常被吞,ok 仍应收到

    assert got == [Ping(n=7)]      # 没被 boom 连累
