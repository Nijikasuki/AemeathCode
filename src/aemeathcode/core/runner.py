import asyncio
import uuid

from datetime import datetime
from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import RunFinishedEvent
from aemeathcode.agent.events.printer import EventLogger
from aemeathcode.agent.events.writer import FileWriter
from aemeathcode.agent.llm.provider import AnthropicProvider
from aemeathcode.agent.tools import registry
from aemeathcode.core.config import get_config, get_data_dir
from aemeathcode.agent.loop import Agent
from aemeathcode.core.context import ExecutionContext, RunServices
from aemeathcode.core.trace.provider import TracingProvider
from aemeathcode.core.trace.writer import TraceWriter
from aemeathcode.core.compact.compact import Compactor
from aemeathcode.core.memory.loader import load_project_memory
from aemeathcode.transport.approver import Approver


class Runner:
    def __init__(self,broadcaster,session_manager,note_store,approval_registry,permissions_manager,profile_store,skill_store):
        self._tasks: set[asyncio.Task] = set()
        self._broadcaster = broadcaster
        self._session_manager = session_manager
        self._note_store = note_store
        self._approval_registry = approval_registry
        self._permissions_manager = permissions_manager
        self._profile_store = profile_store
        self._skill_store = skill_store

    def start_run(self,goal:str,session_id:str,writer)->str:
        bus = EventBus()
        run_time = datetime.now().strftime("%Y%m%d_%H%M%S")

        run_dir = get_data_dir() / "run"
        run_dir.mkdir(parents=True, exist_ok=True)   # FileWriter/TraceWriter 用裸 open,不自建目录

        file_writer = FileWriter(run_dir / f"events_{run_time}.ndjson")
        printer = EventLogger()

        trace_writer = TraceWriter(run_dir / f"traces_{run_time}.ndjson")

        provider = TracingProvider(inner=AnthropicProvider(model = get_config().model,
                                                           note_store=self._note_store,
                                                           project_memory=load_project_memory(get_data_dir()),
                                                           skills_catalog=self._skill_store.catalog_text()),
                                   trace=trace_writer)

        approver = Approver(writer=writer,registry=self._approval_registry)
        compactor = Compactor(provider=provider)
        run_id = str(uuid.uuid4())
        self._session_manager.mark_active(session_id)
        history = self._session_manager.build_history(session_id)
        runtime = self._session_manager.get(session_id)
        if not runtime.session.run_ids:  # 还没有任何 run = 首轮
            self._session_manager.set_title(session_id, goal.strip()[:30])
        self._session_manager.add_run(session_id, run_id)

        services = RunServices(note_store=self._note_store,permission_manager=self._permissions_manager,provider=provider,compactor=compactor,
                               broadcaster=self._broadcaster,approver=approver,trace=trace_writer,writer=writer,profile_store=self._profile_store,skill_store=self._skill_store)
        ctx = ExecutionContext(goal=goal,max_steps=get_config().max_steps,run_id=run_id,messages=history,tasks=runtime.tasks,services=services)

        agent = Agent(ctx=ctx,provider=provider, registry=registry, bus=bus,compactor=compactor)

        bus.subscribe(file_writer.write)
        bus.subscribe(printer.handle)
        bus.subscribe(self._broadcaster.handle)

        task = asyncio.create_task(self._run_guarded(agent, bus,session_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run_id

    async def _run_guarded(self,agent, bus,session_id):

        if agent.ctx.services.trace is not None:
            agent.ctx.services.trace.start()
        try:
            await agent.loop()
        except Exception as e:
            await bus.publish(RunFinishedEvent(status="error", run_id=agent.ctx.run_id, steps=0,content=f"错误:{e}",
                                               input_tokens=agent.ctx.total_input_tokens,output_tokens=agent.ctx.total_output_tokens,cache_read=agent.ctx.total_cache_read))
        finally:
            increment = agent.ctx.record
            increment = self._sanitize(increment)
            self._session_manager.append_run_messages(session_id=session_id,run_id=agent.ctx.run_id,increment=increment)
            self._session_manager.add_token(session_id=session_id,
                                            input_tokens=agent.ctx.total_input_tokens,
                                            output_tokens=agent.ctx.total_output_tokens,
                                            cache_read=agent.ctx.total_cache_read)
            self._session_manager.mark_waiting(session_id=session_id)
            if agent.ctx.services.trace is not None:
                await agent.ctx.services.trace.stop()

    def _sanitize(self,increment:list[dict])->list[dict]:
        """
        给落单的 tool_use 补上 tool_result。
        run 若在"tool_use 已发出、tool_result 还没回填"的中途被 cancel,
        这段残缺增量存进历史后,下轮发给 LLM 会因"tool_use 找不到配对的 tool_result"而 400。

        修法:在【最后一条】assistant 里找出所有未闭合的 tool_use,追加一条 user 消息,
        给每个补一个 is_error 的"运行中断" tool_result,让配对重新合法。
        """
        if increment and increment[-1]["role"]=="assistant":
            content = increment[-1]["content"]
            tools_result = []
            for b in content:
                if b.get("type") == "tool_use":
                    tools_result.append({"type":"tool_result","tool_use_id":b.get("id"),"content":"运行中断","is_error":True})
            if tools_result:
                increment.append({"role":"user","content":tools_result})
        return increment
