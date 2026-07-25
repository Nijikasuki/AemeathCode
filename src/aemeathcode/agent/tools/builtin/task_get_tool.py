
from aemeathcode.agent.tools.base import BaseTool, ToolResult


class TaskGetTool(BaseTool):
    name = "task_get"
    description = "用于根据id获取task"

    input_schema = {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "用于获取task的id，一个id对应一个task"
            }
        },
        "required": ["id"]
    }

    async def invoke(self,params,ctx)-> ToolResult:
        try:
            task_id=params["id"]
            task = ctx.tasks.get(task_id)
            if task is None:
                return ToolResult(
                    content="错误：未知id",
                    is_error=True,
                    error_type="UnknownId"
                )
            return ToolResult(
                content=task.to_line(),
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )