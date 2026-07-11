from dataclasses import dataclass,field

@dataclass
class ToolCallBlock:
    id:str
    name:str
    input:dict

@dataclass
class UsageStats:
    input_tokens:int
    output_tokens:int

@dataclass
class LlmResponse:
    stop_reason:str
    tool_calls: list[ToolCallBlock] = field(default_factory=list)
    text: str = ""
    usage: UsageStats | None = None
