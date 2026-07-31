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
from aemeathcode.core.trace.provider import TracingProvider
from aemeathcode.core.trace.writer import TraceWriter


class Runner:
    def __init__(self,broadcaster,session_manager,note_store):
        self._tasks: set[asyncio.Task] = set()
        self._broadcaster = broadcaster
        self._session_manager = session_manager
        self._note_store = note_store

    def start_run(self,goal:str,session_id:str)->str:
        bus = EventBus()
        run_time = datetime.now().strftime("%Y%m%d_%H%M%S")

        file_writer = FileWriter(Path(f"/home/administrator/cc_learn/AemeathCode/run/events_{run_time}.ndjson"))
        printer = EventLogger()

        trace_writer = TraceWriter(Path(f"/home/administrator/cc_learn/AemeathCode/run/traces_{run_time}.ndjson"))

        provider = TracingProvider(inner=AnthropicProvider(model = get_config().model,note_store=self._note_store),
                                   trace=trace_writer)


        run_id = str(uuid.uuid4())
        self._session_manager.mark_active(session_id)
        history = self._session_manager.build_history(session_id)
        runtime = self._session_manager.get(session_id)
        if not runtime.session.run_ids:  # 还没有任何 run = 首轮
            self._session_manager.set_title(session_id, goal.strip()[:30])
        self._session_manager.add_run(session_id, run_id)
        boundary = len(history)

        ctx = ExecutionContext(goal=goal,max_steps=get_config().max_steps,run_id=run_id,trace=trace_writer,messages=history,tasks=runtime.tasks,note_store=self._note_store)

        agent = Agent(ctx=ctx,provider=provider, registry=registry, bus=bus)

        bus.subscribe(file_writer.write)
        bus.subscribe(printer.handle)
        bus.subscribe(self._broadcaster.handle)

        task = asyncio.create_task(self._run_guarded(agent, bus,session_id,boundary))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run_id

    async def _run_guarded(self,agent, bus,session_id,boundary):

        if agent.ctx.trace is not None:
            agent.ctx.trace.start()
        try:
            await agent.loop()
        except Exception as e:
            await bus.publish(RunFinishedEvent(status="error", run_id=agent.ctx.run_id, steps=0,content=f"错误:{e}",
                                               input_tokens=agent.ctx.total_input_tokens,output_tokens=agent.ctx.total_output_tokens,cache_read=agent.ctx.total_cache_read))
        finally:
            increment = agent.ctx.messages[boundary:]
            self._session_manager.append_run_messages(session_id=session_id,run_id=agent.ctx.run_id,increment=increment)
            self._session_manager.add_token(session_id=session_id,
                                            input_tokens=agent.ctx.total_input_tokens,
                                            output_tokens=agent.ctx.total_output_tokens,
                                            cache_read=agent.ctx.total_cache_read)
            self._session_manager.mark_waiting(session_id=session_id)
            if agent.ctx.trace is not None:
                await agent.ctx.trace.stop()
