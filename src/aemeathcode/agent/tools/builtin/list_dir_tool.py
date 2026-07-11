from aemeathcode.agent.tools.base import BaseTool, ToolResult
from pathlib import Path

class ListDirTool(BaseTool):
    name = "list_dir"
    description = "用于列出目录下的文件/子目录"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目录的路径"
            }
        },
        "required": ["path"]
    }

    async def invoke(self, param) -> ToolResult:
        try:
            path = param["path"]
            dir_path = Path(path)

            # 1. 判断路径是否存在
            if not dir_path.exists():
                return ToolResult(content="错误：目录不存在", is_error=True, error_type="DirNotFoundError")

            # 2. 判断是不是目录
            if not dir_path.is_dir():
                return ToolResult(content="错误：路径不是目录", is_error=True, error_type="IsNotDirError")

            # 3. 遍历目录
            items = []

            for item in sorted(dir_path.iterdir()):
                if item.is_dir():
                    items.append(f"[DIR]  {item.name}")
                else:
                    items.append(f"[FILE] {item.name}")

            if not items:
                return ToolResult(content="目录为空", is_error=False)

            return ToolResult(content="\n".join(items), is_error=False)
        except PermissionError:
            return ToolResult(content="错误：没有读取权限",is_error=True,error_type="PermissionError")

        except Exception as e:
            return ToolResult(content=f"未知错误：{str(e)}",is_error=True,error_type="Exception")


