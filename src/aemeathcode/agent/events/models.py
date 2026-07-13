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

class ThinkingEvent(BaseModel):
    type: Literal["thinking"] = "thinking"
    content: str
    ts: str = Field(default_factory=lambda: datetime.now().isoformat())
    run_id: str

if __name__ == "__main__":
    print(type(RunStartedEvent(goal="帮我看看",run_id="x").model_dump()))