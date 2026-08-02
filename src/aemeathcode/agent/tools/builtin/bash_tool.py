import asyncio
import os, signal
from aemeathcode.agent.tools.base import BaseTool, ToolResult

_MAX_OUTPUT = 64 * 1024   # 输出上限,超了截断,防灌爆上下文
_DEFAULT_TIMEOUT = 60     # 默认超时秒数
_MAX_TIMEOUT = 120        # 超时上限,LLM 传再大也封顶


class BashTool(BaseTool):
    name = "bash"
    description = "用于跑shell命令"

    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "需要在shell中执行的命令"
            },
            "timeout": {
                "type": "integer",
                "description": f"最长等待秒数(默认 {_DEFAULT_TIMEOUT},最大 {_MAX_TIMEOUT})"
            }
        },
        "required": ["command"]
    }

    def permission_key(self, params) -> str:
        # 粗粒度:按命令首词(程序名)记忆,如 "bash:npm" —— 批过 npm 就别再问 npm
        parts = params.get("command", "").split()
        first = parts[0] if parts else ""
        return f"bash:{first}"

    def permission_detail(self, params) -> str:
        # 给人看的:整条命令
        return params.get("command", "")

    async def invoke(self, params, ctx) -> ToolResult:
        try:
            command = params["command"]
            # 没传用默认;传了也不许超过上限
            timeout = min(int(params.get("timeout") or _DEFAULT_TIMEOUT), _MAX_TIMEOUT)

            proc = await asyncio.create_subprocess_shell(command,
                                                        stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.PIPE,
                                                        start_new_session=True)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                stdout = self._truncate(stdout.decode("utf-8",errors="replace"))
                stderr = self._truncate(stderr.decode("utf-8",errors="replace"))

                if proc.returncode != 0:
                    return ToolResult(content=f"stdout:{stdout},stderr:{stderr},returncode:{proc.returncode}", is_error=True, error_type="command_failed")

                return ToolResult(content=f"stdout:{stdout}", is_error=False)

            except asyncio.TimeoutError:
                return ToolResult(content=f"超时(>{timeout}s)", is_error=True, error_type="timeout")

            finally:
                if proc.returncode is None:  # 还在跑(超时/被取消/异常)→ 收拾掉
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await proc.wait()

        except Exception as e:
            return ToolResult(
                content=f"未知错误：{str(e)}",
                is_error=True,
                error_type="Exception"
            )

    @staticmethod
    def _truncate(text: str) -> str:
        if len(text) > _MAX_OUTPUT:
            return text[:_MAX_OUTPUT] + "\n[已截断]"
        return text
