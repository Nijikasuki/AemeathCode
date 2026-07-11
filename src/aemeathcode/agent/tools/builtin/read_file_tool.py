from aemeathcode.agent.tools.base import BaseTool, ToolResult
from pathlib import Path

class ReadFileTool(BaseTool):
    name = "read_file"
    description = "用于读取文件"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件的路径"
            }
        },
        "required": ["path"]
    }
    max_size = 1024*1024
    async def invoke(self, param) -> ToolResult:
        try:
            path = param["path"]
            file_path = Path(path)

            # 1. 判断路径是否存在
            if not file_path.exists():
                return ToolResult(content="错误：文件不存在",is_error=True,error_type="FileNotFoundError")

            # 2. 判断是不是文件
            if not file_path.is_file():
                return ToolResult(content="错误：路径不是文件",is_error=True,error_type="PathError")

            # 3. 文件大小检查
            size = file_path.stat().st_size

            if size > self.max_size:
                return ToolResult(content=f"错误：文件过大({size} bytes)，超过限制",is_error=True,error_type="FilesizeError")

            # 4. 读取
            with file_path.open("r", encoding="utf-8") as f:
                return ToolResult(content=f.read(),is_error=False)

        except PermissionError:
            return ToolResult(content="错误：没有读取权限",is_error=True,error_type="PermissionError")

        except UnicodeDecodeError:
            return ToolResult(content="错误：文件编码不是UTF-8",is_error=True,error_type="UnicodeDecodeError")

        except Exception as e:
            return ToolResult(content=f"未知错误：{str(e)}",is_error=True,error_type="Exception")


