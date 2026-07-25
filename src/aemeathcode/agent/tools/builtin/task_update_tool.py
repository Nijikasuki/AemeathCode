
from aemeathcode.agent.tools.base import BaseTool, ToolResult


class TaskUpdateTool(BaseTool):
    name = "task_update"
    description = "根据id来对某个task进行状态更新"

    input_schema = {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "用于获取task的id，一个id对应一个task"
            },
            "status": {
                "type": "string",
                "enum": ["pending", "progressing", "completed", "failed"],
                "description":"最新的task的status"
            }
        },
        "required": ["id","status"]
    }

    async def invoke(self,params,ctx)-> ToolResult:
        try:
            task_id = params["id"]
            status = params["status"]

            task = ctx.tasks.get(task_id)
            if task is None:
                return ToolResult(
                    content="错误：未知id",
                    is_error=True,
                    error_type="UnknownId"
                )

            task = ctx.tasks.update(task_id=task_id,status=status)

            return ToolResult(
                content=f"已更新 {task.to_line()}",
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )