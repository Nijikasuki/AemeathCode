import asyncio
from aemeathcode.transport.socket_server import SocketServer
from aemeathcode.core.app import ping_handler, run_handler
from aemeathcode.transport.socket_client import SocketClient

async def main():
    server = SocketServer(host="127.0.0.1", port=9999)
    server.register("ping", ping_handler)
    server.register("run", run_handler)
    await server.start()

    client = SocketClient("127.0.0.1", 9999)
    await client.connect()

    done = asyncio.Event()  # 信号旗

    async def on_event(event):  # 事件处理器
        print(event)
        if event.get("type") == "run.completed":
            done.set()
        else:
            print(f"· {event["type"]}")

    client.on_event(on_event)

    loop_task = asyncio.create_task(client.run_event_loop())  # 分拣室后台跑
    pong = await client.send_command("ping", {})
    print(pong)

    ack = await client.send_command("run", {"goal": "列出当前目录并读一个文件"})
    print("ack:",ack)

    await done.wait()  # 盯着旗，等 run.completed

    loop_task.cancel()  # 收工：停分拣室
    await client.close()
    await server.stop()

if __name__ == '__main__':
    asyncio.run(main())