from pathlib import Path
from aemeathcode.agent.tools.base import BaseTool, ToolResult


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "用于在当前工作目录下新建或者覆盖文件"

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "需要覆盖(新建)文件的路径"
            },
            "content": {
                "type": "string",
                "description": "需要覆盖(新建)文件的内容"
            }
        },
        "required": ["path", "content"]
    }

    async def invoke(self, param,ctx) -> ToolResult:
        try:
            cwd = Path.cwd()

            path = param["path"]
            content = param["content"]

            file_path = (cwd / path).resolve()

            # 防止越界访问工作目录外文件
            if not file_path.is_relative_to(cwd):
                return ToolResult(
                    content="错误:路径不在工作目录下",
                    is_error=True,
                    error_type="PermissionError"
                )

            # 创建父目录
            file_path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            # 写文件
            file_path.write_text(
                content,
                encoding="utf-8"
            )

            return ToolResult(
                content=f"已写入 {file_path.stat().st_size} 字节 → {file_path}",
                is_error=False
            )

        except PermissionError:
            return ToolResult(
                content="错误：没有写入权限",
                is_error=True,
                error_type="PermissionError"
            )

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )