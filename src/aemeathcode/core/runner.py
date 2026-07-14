import asyncio
import uuid

from pathlib import Path
from datetime import datetime
from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import RunFinishedEvent
from aemeathcode.agent.events.printer import EventLogger
from aemeathcode.agent.events.writer import FileWriter
from aemeathcode.agent.llm.provider import AnthropicProvider
from aemeathcode.agent.tools import registry
from aemeathcode.core.config import get_config
from aemeathcode.agent.loop import Agent
from aemeathcode.core.context import ExecutionContext


class Runner:
    def __init__(self,broadcaster):
        self._tasks: set[asyncio.Task] = set()
        self._broadcaster = broadcaster
    def start_run(self,goal:str)->str:
        bus = EventBus()
        run_time = datetime.now().strftime("%Y%m%d_%H%M%S")

        file_writer = FileWriter(Path(f"/home/administrator/cc_learn/AemeathCode/run/events_{run_time}.ndjson"))
        printer = EventLogger()

        provider = AnthropicProvider(get_config().model)

        run_id = str(uuid.uuid4())
        ctx = ExecutionContext(goal=goal,max_steps=get_config().max_steps,run_id=run_id)
        agent = Agent(ctx=ctx,provider=provider, registry=registry, bus=bus)

        bus.subscribe(file_writer.write)
        bus.subscribe(printer.handle)
        bus.subscribe(self._broadcaster.handle)

        task = asyncio.create_task(self._run_guarded(agent, bus))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run_id

    @staticmethod
    async def _run_guarded(agent, bus):
        try:
            await agent.loop()
        except Exception as e:
            await bus.publish(RunFinishedEvent(status="error", run_id=agent.ctx.run_id, steps=0,content=f"错误:{e}"))

