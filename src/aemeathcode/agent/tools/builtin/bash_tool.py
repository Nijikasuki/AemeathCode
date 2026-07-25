import asyncio
from aemeathcode.agent.tools.base import BaseTool, ToolResult

class BashTool(BaseTool):
    name = "bash"
    description = "用于跑shell命令"

    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "需要在shell中执行的命令"
            }
        },
        "required": ["command"]
    }


    async def invoke(self, param,ctx) -> ToolResult:
        try:
            command = param["command"]

            proc = await asyncio.create_subprocess_shell(command,
                                                  stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
                stdout = stdout.decode("utf-8")
                stderr = stderr.decode("utf-8")

                if proc.returncode != 0:
                    return ToolResult(content=f"stdout:{stdout},stderr:{stderr},returncode:{proc.returncode}", is_error=True, error_type="command_failed")

                return ToolResult(content=f"stdout:{stdout}", is_error=False)

            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(content="超时", is_error=True, error_type="timeout")

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )