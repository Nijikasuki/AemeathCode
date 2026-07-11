import asyncio
from datetime import datetime
import logging
import signal
from pathlib import Path
from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.printer import ConsolePrinter
from aemeathcode.agent.events.writer import FileWriter
from aemeathcode.agent.llm.provider import AnthropicProvider
from aemeathcode.agent.tools import registry
from aemeathcode.core.config import get_config
from aemeathcode.core.logging_setup import setup_logging
from aemeathcode.transport.socket_server import SocketServer
from aemeathcode.agent.loop import Agent

logger = logging.getLogger(__name__)

async def ping_handler(params):
    return "pong"

async def run_handler(params):
    goal = params.get("goal")
    if not goal:
        return "错误:缺少 goal 参数"
    bus = EventBus()
    run_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    writer = FileWriter(Path(f"/home/administrator/cc_learn/AemeathCode/run/events_{run_time}.ndjson"))
    printer = ConsolePrinter()
    provider = AnthropicProvider(get_config().model)
    agent = Agent(provider=provider,registry=registry,bus=bus,goal=goal)
    bus.subscribe(writer.write)
    bus.subscribe(printer.handle)
    return await agent.loop()

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