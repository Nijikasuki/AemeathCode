from dataclasses import dataclass, field

from aemeathcode.agent.llm.types import LlmResponse, UsageStats
from aemeathcode.core.memory.note import NoteStore
from aemeathcode.core.permissions.manager import PermissionsManager
from aemeathcode.core.task.manager import TaskManager
from aemeathcode.core.trace.writer import TraceWriter
from aemeathcode.transport.approver import Approver

@dataclass
class ExecutionContext:
    goal: str
    max_steps: int
    run_id: str
    tasks: TaskManager
    note_store: NoteStore
    permission_manager: PermissionsManager
    messages: list[dict]
    record: list[dict] = field(default_factory=list)
    reason: str|None = None
    status: str = "running"
    step :int = 0
    total_input_tokens :int = 0
    total_output_tokens :int = 0
    total_cache_read :int = 0
    trace: TraceWriter | None = None
    approver: Approver | None = None
    last_usage: UsageStats | None = None

    def __post_init__(self):
        self.messages.append({"role": "user", "content": self.goal})
        self.record.append({"role": "user", "content": self.goal})

    def add_assistant_message(self,content:list):
        self.messages.append({"role": "assistant", "content": content})
        self.record.append({"role": "assistant", "content": content})

    def add_tool_results(self,tool_result:list):
        self.messages.append({"role": "user", "content": tool_result})
        self.record.append({"role": "user", "content": tool_result})

    def mark_success(self):
        self.status = "success"

    def mark_failed(self,reason:str):
        self.status = "error"
        self.reason = reason

    def is_done(self):
        return self.status != "running"

    def token_add(self,resp:LlmResponse):
        if resp.usage is not None:
            self.total_input_tokens += resp.usage.input_tokens
            self.total_output_tokens += resp.usage.output_tokens
            self.total_cache_read += resp.usage.cache_read_input_tokens
            self.last_usage = resp.usage