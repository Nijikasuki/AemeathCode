import asyncio
import logging
import signal

from aemeathcode.core.config import get_config
from aemeathcode.core.logging_setup import setup_logging
from aemeathcode.core.memory.note import NoteStore
from aemeathcode.core.runner import Runner
from aemeathcode.core.session.manager import SessionManager
from aemeathcode.core.session.store import SessionStore
from pathlib import Path
from aemeathcode.transport.context import RequestContext
from aemeathcode.transport.socket_server import SocketServer
from aemeathcode.transport.ipc_broadcaster import IpcEventBroadcaster,Subscriber

logger = logging.getLogger(__name__)
broadcaster = IpcEventBroadcaster()
store = SessionStore(Path("sessions"))
note_store = NoteStore(Path("."))
session_manager = SessionManager(store)
runner = Runner(broadcaster,session_manager,note_store)

async def ping_handler(ctx:RequestContext)->str:
    return "pong"

async def run_handler(ctx:RequestContext)->dict|str:
    goal = ctx.params.get("goal")
    session_id = ctx.params.get("session_id")
    if not goal:
        return "错误:缺少 goal 参数"
    if not session_id:
        return "错误:缺少 session_id 参数"
    if session_manager.get(session_id) is None:
        return "错误:会话不存在"

    run_id = runner.start_run(goal=goal,session_id=session_id)
    broadcaster.subscribe(Subscriber(writer = ctx.writer,scope=f"run:{run_id}",topics=["*"]))
    return {"run_id": run_id}

async def watch_handler(ctx:RequestContext)->dict:
    scope = ctx.params.get("scope", "global")
    topics = ctx.params.get("topics", ["*"])
    broadcaster.subscribe(Subscriber(writer=ctx.writer,scope=scope,topics=topics))
    return {"subscribed": scope}

async def session_create_handler(ctx:RequestContext)->dict:
    mode = ctx.params.get("mode","multi_turn")
    session_runtime = session_manager.create(mode=mode)
    return {"session_id": session_runtime.session.id}

async def session_list_handler(ctx:RequestContext)->dict:
    # 纯读磁盘,不碰内存状态,直接问 store
    return {"sessions": store.list_sessions()}

async def session_resume_handler(ctx:RequestContext)->dict|str:
    session_id = ctx.params.get("session_id")
    if not session_id:
        return "错误:缺少 session_id 参数"
    try:
        runtime = session_manager.resume(session_id)   # 内存没有就从磁盘 load 进来
    except FileNotFoundError:
        return "错误:会话不存在"
    # 关键:把历史一起返回,客户端才能把旧对话重放到屏幕
    return {
        "session_id": session_id,
        "title": runtime.session.title,
        "history": session_manager.build_history(session_id),
    }

async def session_usage_handler(ctx:RequestContext)->dict|str:
    session_id = ctx.params.get("session_id")
    if not session_id:
        return "错误:缺少 session_id 参数"
    runtime = session_manager.get(session_id)
    if runtime is None:
        return "错误:会话不存在"
    return {
        "input_tokens": runtime.total_input_tokens,
        "output_tokens": runtime.total_output_tokens,
        "cache_read": runtime.total_cache_read,
    }


async def main():
    config = get_config()
    setup_logging(config)
    server = SocketServer(host=config.host,port=config.port,broadcaster=broadcaster)
    server.register(method="ping",handler=ping_handler)
    server.register(method="run",handler=run_handler)
    server.register(method="watch",handler=watch_handler)
    server.register(method="session.create",handler=session_create_handler)
    server.register(method="session.list",handler=session_list_handler)
    server.register(method="session.resume",handler=session_resume_handler)
    server.register(method="session.usage",handler=session_usage_handler)

    addr = await server.start()
    logger.info("listening on %s", addr)

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, shutdown.set)
    loop.add_signal_handler(signal.SIGTERM, shutdown.set)

    await shutdown.wait()      # ← 平时就停在这,等信号
    await server.stop()        # ← 收到信号才往下,优雅关闭

def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()