import argparse
import asyncio

from aemeathcode.transport.socket_client import SocketClient
from aemeathcode.core.app import main as app_main
from aemeathcode.tui.stream_renderer import StreamRenderer


async def _ping():
    client = SocketClient("127.0.0.1", 9999)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())  # 分拣室后台跑
    pong = await client.send_command("ping", {})
    print(pong)
    loop_task.cancel()  # 收工：停分拣室
    await client.close()

async def _run(goal:str):
    client = SocketClient("127.0.0.1", 9999)
    await client.connect()

    done = asyncio.Event()
    renderer = StreamRenderer()

    async def on_event(event):  # 事件处理器
        renderer.feed(event)
        if event.get("type") == "run.completed":
            done.set()

    client.on_event(on_event)
    loop_task = asyncio.create_task(client.run_event_loop())

    ack = await client.send_command("run", {"goal": goal})
    print(f"🚀 已启动 (run_id={ack['run_id']})")

    await done.wait()  # 盯着旗，等 run.completed

    loop_task.cancel()  # 收工：停分拣室
    await client.close()

async def _watch(scope:str, topics:list[str]):
    client = SocketClient("127.0.0.1", 9999)
    await client.connect()
    renderer = StreamRenderer()

    async def on_event(event):
        renderer.feed(event)

    client.on_event(on_event)
    loop_task = asyncio.create_task(client.run_event_loop())
    ack = await client.send_command("watch", {"scope": scope, "topics": topics})
    print(f"观察模式已启动,scope={ack["subscribed"]}")
    await loop_task

def cmd_ping(args):
    asyncio.run(_ping())

def cmd_core(args):
    asyncio.run(app_main())

def cmd_run(args):
    asyncio.run(_run(args.goal))

def cmd_watch(args):
    asyncio.run(_watch(args.scope, args.topics))

def cmd_tui(args):
    # 延迟导入:只有真进 TUI 才加载 textual,别的子命令不受影响
    from aemeathcode.tui.app import run as run_tui
    run_tui()

def main():
    parser = argparse.ArgumentParser(prog='aemeath')
    # 不传子命令时默认进 TUI(类似 claude code:敲 aemeath 直接进界面)
    parser.set_defaults(func=cmd_tui)
    subparsers = parser.add_subparsers(dest="command")

    p_core = subparsers.add_parser('core')
    p_core.set_defaults(func=cmd_core)

    p_run = subparsers.add_parser('run')
    p_run.add_argument("goal")
    p_run.set_defaults(func=cmd_run)

    p_ping = subparsers.add_parser("ping")
    p_ping.set_defaults(func=cmd_ping)

    p_watch = subparsers.add_parser('watch')
    p_watch.add_argument("--scope", default="global")
    p_watch.add_argument("--topics", default=["*"])
    p_watch.set_defaults(func=cmd_watch)

    p_tui = subparsers.add_parser('tui')     # 显式写法,和裸 aemeath 等价
    p_tui.set_defaults(func=cmd_tui)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()