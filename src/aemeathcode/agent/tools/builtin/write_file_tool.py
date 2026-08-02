from pathlib import Path
from aemeathcode.agent.tools.base import BaseTool, ToolResult

_MAX_BYTES = 1 * 1024 * 1024  # 内容上限 1MB,防超大写入


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

    def permission_key(self, params) -> str:
        # 粗粒度:按目标文件的父目录记忆,如 "write_file:/home/x/proj/src"
        # —— 批过往某目录写,同目录别再问。解析成绝对路径,免得 "a/b" 与 "./a/b" 算成两个 key
        parent = (Path.cwd() / params.get("path", "")).resolve().parent
        return f"write_file:{parent}"

    def permission_detail(self, params) -> str:
        # 给人看的:目标路径
        return params.get("path", "")

    async def invoke(self, params,ctx) -> ToolResult:
        try:
            cwd = Path.cwd()

            path = params["path"]
            content = params["content"]

            # 内容超 1MB 拒绝,防灌爆磁盘/上下文
            if len(content.encode("utf-8")) > _MAX_BYTES:
                return ToolResult(
                    content=f"错误:内容过大({len(content.encode('utf-8'))} 字节,上限 1MB)",
                    is_error=True,
                    error_type="content_too_large"
                )

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