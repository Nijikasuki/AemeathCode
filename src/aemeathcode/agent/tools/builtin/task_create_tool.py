
from aemeathcode.agent.tools.base import BaseTool, ToolResult


class TaskCreateTool(BaseTool):
    name = "task_create"
    description = "用于新建task"

    input_schema = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "新建的task需要执行的内容"
            }
        },
        "required": ["content"]
    }

    async def invoke(self,params,ctx)-> ToolResult:
        try:
            content=params["content"]
            task = ctx.tasks.create(content)
            return ToolResult(
                content=f"已创建 {task.to_line()}",
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )