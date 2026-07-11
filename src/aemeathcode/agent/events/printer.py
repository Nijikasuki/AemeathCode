from pydantic import BaseModel


def _short(text: str, limit: int = 150) -> str:
    """把多行/超长内容压成一行、截断,便于终端阅读。"""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"


class ConsolePrinter:
    async def handle(self, event: BaseModel) -> None:
        if event.type == "run.started":
            print(f"\n🎯 目标: {event.goal}")
        elif event.type == "thinking":
            print(f"🧠 思考: {_short(event.content)}")
        elif event.type == "tool.call_started":
            print(f"🔧 调用 {event.tool_name}  参数={event.params}")
        elif event.type == "tool.call_finished":
            icon = "❌" if event.is_error else "📄"
            print(f"{icon} 结果: {_short(event.content)}")
        elif event.type == "run.completed":
            icon = "✅" if event.status == "success" else "⚠️"
            print(f"{icon} 完成 (状态={event.status}, 步数={event.steps})\n")
        else:
            print(f"· {event.type}")
