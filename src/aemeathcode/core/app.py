import asyncio
import logging
import signal

from aemeathcode.core.config import get_config
from aemeathcode.core.logging_setup import setup_logging
from aemeathcode.core.runner import Runner
from aemeathcode.transport.context import RequestContext
from aemeathcode.transport.socket_server import SocketServer


logger = logging.getLogger(__name__)
runner = Runner()

async def ping_handler(ctx:RequestContext)->str:
    return "pong"

async def run_handler(ctx:RequestContext)->dict|str:
    goal = ctx.params.get("goal")
    if not goal:
        return "错误:缺少 goal 参数"
    run_id = runner.start_run(goal=goal,writer=ctx.writer)
    return {"run_id": run_id}

async def main():
    config = get_config()
    setup_logging(config)
    server = SocketServer(host=config.host,port=config.port)
    server.register("ping",ping_handler)
    server.register("run",run_handler)

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