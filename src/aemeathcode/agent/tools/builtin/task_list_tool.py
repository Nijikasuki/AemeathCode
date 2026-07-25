
from aemeathcode.agent.tools.base import BaseTool, ToolResult


class TaskListTool(BaseTool):
    name = "task_list"
    description = "用于列出当前的所有task"

    input_schema = {
        "type": "object",
        "properties": {}
    }

    async def invoke(self,params,ctx)-> ToolResult:
        try:
            tasks = ctx.tasks.list()
            if not tasks:
                return ToolResult(content="当前没有任务", is_error=False)
            lines = "\n".join(t.to_line() for t in tasks)
            return ToolResult(content=lines, is_error=False)

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )