from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class ToolResult:
    content:str
    is_error:bool = False
    error_type:str |None = None


class BaseTool(ABC):
    name:str
    description:str
    input_schema:dict

    @abstractmethod
    async def invoke(self, params) -> ToolResult:
        pass
