from dataclasses import dataclass
from abc import ABC, abstractmethod
from aemeathcode.core.context import ExecutionContext

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
    async def invoke(self, params,ctx:ExecutionContext) -> ToolResult:
        pass

    def permission_key(self, params) -> str:
        return self.name  # 默认整工具粒度

    def permission_detail(self, params) -> str:
        return str(params)