from pydantic import BaseModel,Field
from typing import Literal
from datetime import datetime

class ToolCallStartEvent(BaseModel):
    type: Literal["tool.call_started"] = "tool.call_started"
    tool_use_id: str
    tool_name: str
    params: dict
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

class RunStartedEvent(BaseModel):
    type: Literal["run.started"] = "run.started"
    goal: str
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

class ToolCallFinishedEvent(BaseModel):
    type: Literal["tool.call_finished"] = "tool.call_finished"
    tool_use_id: str
    is_error: bool
    content: str
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

class RunFinishedEvent(BaseModel):
    type: Literal["run.completed"] = "run.completed"
    status: str
    steps: int
    content: str
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str
    input_tokens:int = 0
    output_tokens:int = 0
    cache_read:int = 0

class ThinkingEvent(BaseModel):
    type: Literal["llm.thinking"] = "llm.thinking"
    content: str
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

class LlmTokenEvent(BaseModel):
    type: Literal["llm.token"] = "llm.token"
    content: str
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

class ContextUsageEvent(BaseModel):
    # 每次 chat 后推一发:当前上下文水位(used)/ 窗口(window),给前端画进度条
    type: Literal["context.usage"] = "context.usage"
    used: int
    window: int
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

class CompactionStartedEvent(BaseModel):
    # 压缩【开始】时推一发(await 概括之前):前端挂"正在压缩"指示器
    type: Literal["context.compacting"] = "context.compacting"
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

class CompactionEvent(BaseModel):
    # 压缩【完成】时推一发:压缩前后的消息条数,前端撤掉指示器 + 提示
    type: Literal["context.compacted"] = "context.compacted"
    before: int
    after: int
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

class SubAgentStartedEvent(BaseModel):
    type: Literal["subagent.started"] = "subagent.started"
    parent_tool_use_id: str
    run_id: str
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())