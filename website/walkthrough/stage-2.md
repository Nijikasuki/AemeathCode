# 双进程 + 多路复用

> 对应 tag:[`stage-2`](https://github.com/Nijikasuki/AemeathCode/tree/stage-2) ·
> 改动:[`stage-1...stage-2`](https://github.com/Nijikasuki/AemeathCode/compare/stage-1...stage-2)(15 个文件,+394 −111)

## 这一阶段要解决什么

[上一篇](./stage-1)结束时,客户端发一个请求、等一个响应,中间什么都看不见 —— 一个 run 可能跑一分钟,
界面就一直卡着。

这一篇要做到:**同一根连接上,既能发请求等回执,又能随时收到 daemon 主动推来的事件**
(模型在想什么、调了哪个工具、结果是什么)。

打个比方:之前像打电话问路,问一句等一句;现在像在一个对讲频道里 ——
你随时能发问,对面也随时能播报,而且你得能分清「这句是在回我的问题」还是「这是一条广播」。

| | 之前 | 现在 |
|---|---|---|
| 通信形态 | 一请求一响应 | 请求/响应 + 服务端推送,共用一条连接 |
| run 怎么跑 | 阻塞到跑完才回 | 后台作业,秒回 `run_id`,过程用事件流推 |
| 谁能看 | 只有发起者 | 发起者 + 任意「旁观者」(`watch`) |

## 核心:客户端的「分拣室」

客户端只有一条读路径,读到的每一行可能是两种东西:**某个请求的回执**,或**一条事件**。
关键是请求发出去以后,怎么把后来读到的回执「对号入座」。

### 发请求:领号 + 记小本子

[`socket_client.py#L31-L37`](https://github.com/Nijikasuki/AemeathCode/blob/stage-2/src/aemeathcode/transport/socket_client.py#L31-L37)

```python {2-4,7}
async def send_command(self,method,params)-> Any:
    req_id = uuid.uuid4().hex                               # 领一个唯一号
    fut = asyncio.get_running_loop().create_future()        # 开一张「待取件」单
    self._pending[req_id] = fut                             # 记在小本子上
    self._writer.write(JsonRpcRequest(id=req_id,method=method,params=params).model_dump_json().encode() + b'\n')
    await self._writer.drain()
    return await fut          # 在这里睡,直到读循环把结果放进 fut
```

`send_command` **自己不读连接**。它只是把号码和一张空的 `Future` 登记好,然后睡在 `await fut` 上。

### 读循环:按号码唤醒

[`socket_client.py#L57-L70`](https://github.com/Nijikasuki/AemeathCode/blob/stage-2/src/aemeathcode/transport/socket_client.py#L57-L70)

```python {3,7-9,14}
async def _dispatch(self,line):
    msg = json.loads(line)
    if msg.get("kind") == "event":                # ① 广播:交给所有事件处理器
        event = msg["event"]
        for handler in self._event_handlers:
            await handler(event)
    elif "jsonrpc" in msg:                        # ② 回执:按 id 找到那张待取件单
        req_id = msg["id"]
        fut = self._pending.pop(req_id,None)
        if fut and not fut.done():
            if "error" in msg:
                fut.set_exception(IpcError(msg["error"]["code"],msg["error"]["message"]))
            else:
                fut.set_result(msg.get("result"))  # 唤醒睡在 await fut 上的协程
```

这就是「多路复用」的全部秘密:**发请求的路径和收结果的路径是两条**,中间靠 `req_id → Future` 这本小本子连起来。

::: details 展开:时序图(一个请求的完整一生)
```
send_command 协程              读循环 run_event_loop              daemon
──────────────────            ─────────────────────              ──────
领号 abc,挂 Future
写出请求 ───────────────────────────────────────────────────────▶
await fut(睡)                  readline() 读到 event ◀────────── 推事件
                               └ 交给 on_event 处理器
                               readline() 读到 {id: abc} ◀────── 回执
                               └ _pending.pop("abc").set_result()
被唤醒,拿到结果
```
:::

::: warning 踩过的坑:在事件处理器里 await send_command = 死锁
`_dispatch` 是读循环**亲自** `await` 的。如果某个事件处理器里又 `await send_command(...)`,
它要等的回执只能由读循环送达 —— 而读循环此刻正卡在等这个处理器返回。**自己等自己,永久挂起。**

这个 bug 后来在 v0.2.0 的 TUI 里真的发生过:第一个 run 结束后事件流永久停摆。
修法是把这类调用丢进独立的 worker,不在读循环的调用链里 await。
:::

::: tip 断线时别让任何人永远睡着
[`run_event_loop` 的 `finally`](https://github.com/Nijikasuki/AemeathCode/blob/stage-2/src/aemeathcode/transport/socket_client.py#L47-L51)
会把小本子上所有还没取件的 `Future` 统一 `set_exception(ConnectionError)`。
否则连接一断,所有在等回执的协程会永远挂在 `await fut` 上。
:::

## 服务端:谁该收到这条事件

事件不是发给所有人的。每个订阅者带两个过滤条件:**scope**(哪个 run)和 **topics**(哪类事件)。

[`ipc_broadcaster.py#L38-L51`](https://github.com/Nijikasuki/AemeathCode/blob/stage-2/src/aemeathcode/transport/ipc_broadcaster.py#L38-L51)

```python {5}
async def handle(self, event):
    data = EventEnvelope(event=event.model_dump()).model_dump_json().encode() + b"\n"
    run_id = event.run_id
    dead = []
    for subscriber in list(self._subscribers):    # 遍历快照,不是原列表
        if not self._match(run_id=run_id, scope=subscriber.scope): continue
        if not self._match_topic(event_type=event.type, topics=subscriber.topics): continue
        try:
            subscriber.writer.write(data)
            await subscriber.writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            dead.append(subscriber.writer)          # 先记下死连接,遍历完再清
    for writer in dead:
        self.unsubscribe(writer)
```

高亮那一行的 `list(...)` 不是多余的:循环里有 `await drain()`,**在它让出控制权的那一刻,
别的协程可能正在增删订阅者**。直接遍历原列表会遇到「遍历中被修改」。

## 这一阶段学到的

- 请求/响应配对 = **唯一 id + Future + 另一条读路径负责 resolve**。后来[权限审批](./stage-5)的反向请求、[MCP 客户端](./stage-7),都是这套机制的镜像
- `asyncio.create_task` 起的后台任务要把引用接住,否则可能被 GC 回收
- 遍历共享集合时如果中间有 `await`,要遍历快照
