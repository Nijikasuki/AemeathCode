from asyncio import StreamWriter
from dataclasses import dataclass, field

from aemeathcode.agent.llm.base import LLMProvider
from aemeathcode.agent.llm.types import LlmResponse, UsageStats
from aemeathcode.core.agents.loader import ProfileStore
from aemeathcode.core.compact.compact import Compactor
from aemeathcode.core.memory.note import NoteStore
from aemeathcode.core.permissions.manager import PermissionsManager
from aemeathcode.core.task.manager import TaskManager
from aemeathcode.core.trace.writer import TraceWriter
from aemeathcode.transport.approver import Approver
from aemeathcode.transport.ipc_broadcaster import IpcEventBroadcaster


@dataclass
class RunServices:
    """一个 run 借来的外部依赖 —— 不是 run 自身的状态,而是它【用】的东西。
    subagent 整包共享:sub_ctx.services = 父 ctx.services(服务借父)。"""
    note_store: NoteStore
    permission_manager: PermissionsManager
    provider: LLMProvider
    compactor: Compactor
    broadcaster: IpcEventBroadcaster
    profile_store: ProfileStore
    approver: Approver | None = None
    trace: TraceWriter | None = None
    writer: StreamWriter | None = None   # 发起该 run 的客户端连接(反向审批 / 子 run 观测订阅用)


@dataclass
class ExecutionContext:
    # ---- 状态:run 的本体,每个 run/subagent 各建一份(状态各建)----
    goal: str
    max_steps: int
    run_id: str
    tasks: TaskManager
    messages: list[dict]
    # ---- 服务:借来的外部依赖(整包挂这里)----
    services: RunServices
    # ---- 运行中累积的状态 ----
    record: list[dict] = field(default_factory=list)
    reason: str | None = None
    status: str = "running"
    step: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read: int = 0
    last_usage: UsageStats | None = None
    current_tool_use_id: str | None = None

    def __post_init__(self):
        self.messages.append({"role": "user", "content": self.goal})
        self.record.append({"role": "user", "content": self.goal})

    def add_assistant_message(self, content: list):
        self.messages.append({"role": "assistant", "content": content})
        self.record.append({"role": "assistant", "content": content})

    def add_tool_results(self, tool_result: list):
        self.messages.append({"role": "user", "content": tool_result})
        self.record.append({"role": "user", "content": tool_result})

    def mark_success(self):
        self.status = "success"

    def mark_failed(self, reason: str):
        self.status = "error"
        self.reason = reason

    def is_done(self):
        return self.status != "running"

    def token_add(self, resp: LlmResponse):
        if resp.usage is not None:
            self.total_input_tokens += resp.usage.input_tokens
            self.total_output_tokens += resp.usage.output_tokens
            self.total_cache_read += resp.usage.cache_read_input_tokens
            self.last_usage = resp.usage
