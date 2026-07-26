from pydantic import BaseModel
from typing import Literal

class TraceRecord(BaseModel):
    run_id: str
    category: Literal["llm", "tool"]
    name: str
    ts: str
    duration_ms: float
    status: Literal["ok","error"]
    error: str|None = None