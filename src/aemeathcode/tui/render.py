def _short(text: str, limit: int = 150) -> str:
    """把多行/超长内容压成一行、截断,便于终端阅读。"""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"

def render(event: dict) -> str:      # 只 return 字符串,不 print
    tag = event["run_id"][:8]          # 取前 8 位当短标签
    prefix = f"[{tag}] "
    if event["type"] == "run.started":
        return f"\n{prefix}🎯 目标: {event['goal']}"
    elif event["type"] == "thinking":
        return f"{prefix}🧠 思考: {_short(event["content"])}"
    elif event["type"] == "tool.call_started":
        return f"{prefix}🔧 调用 {event["tool_name"]}  参数={event["params"]}"
    elif event["type"] == "tool.call_finished":
        icon = "❌" if event["is_error"] else "📄"
        return f"{prefix}{icon} 结果: {_short(event['content'])}"
    elif event["type"] == "run.completed":
        icon = "✅" if event["status"] == "success" else "⚠️"
        return f"{prefix}{icon} 完成 (状态={event['status']}, 步数={event['steps']})\n\n{event['content']}"
    else:
        return f"· {prefix}{event["type"]}"