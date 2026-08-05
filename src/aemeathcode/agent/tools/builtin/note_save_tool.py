
from aemeathcode.agent.tools.base import BaseTool, ToolResult


class NoteSaveTool(BaseTool):
    name = "note_save"
    description = "当出现值得【长期、跨对话】记住的事实、用户偏好或项目约定时,调用此工具记录。记录的内容以后每轮会自动带入上下文,所以别重复记同一件事。"

    input_schema = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "需要记录的重要事实"
            }
        },
        "required": ["content"]
    }

    async def invoke(self,params,ctx)-> ToolResult:
        try:
            content=params["content"]
            ctx.services.note_store.append(content)
            return ToolResult(
                content=f" 已记住:{content}",
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )