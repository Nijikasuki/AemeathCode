def _short(text: str, limit: int = 150) -> str:
    """把多行/超长内容压成一行、截断,便于终端阅读。"""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"

def render(event: dict) -> str:      # 只 return 字符串,不 print
    tag = event["run_id"][:8]          # 取前 8 位当短标签
    prefix = f"[{tag}] "
    if event["type"] == "run.started":
        return f"\n{prefix}🎯 目标: {event['goal']}"
    elif event["type"] == "tool.call_started":
        return f"{prefix}🔧 调用 {event["tool_name"]}  参数={event["params"]}"
    elif event["type"] == "tool.call_finished":
        icon = "❌" if event["is_error"] else "📄"
        return f"{prefix}{icon} 结果: {_short(event['content'])}"
    elif event["type"] == "run.completed":
        icon = "✅" if event["status"] == "success" else "⚠️"
        return f"{prefix}{icon} 完成 (状态={event['status']}, 步数={event['steps']}, input_tokens={event['input_tokens']}, output_tokens={event['output_tokens']}, cache_read={event['cache_read']})"
    else:
        return f"· {prefix}{event["type"]}"


def event_markup(event: dict) -> str:
    """TUI 版:带 Rich 行内标记,同一行内可以逐词着色。

    CLI 走上面的 render()(纯文本),TUI 走这个 —— 同一份事件,两种呈现。
    tool.* 事件由 ToolCallBlock 单独渲染,不走这里。
    """
    etype = event.get("type", "")
    if etype == "run.started":
        return f"[dim]目标[/dim]  [bold]{event.get('goal', '')}[/bold]"
    if etype == "run.completed":
        ok = event.get("status") == "success"
        color, icon = ("$success", "✓") if ok else ("$error", "✗")
        return (
            f"[{color}]{icon} {event.get('status', '')}[/{color}]"
            f"  [dim]{event.get('steps', 0)} 步 · in {event.get('input_tokens', 0)}"
            f" · cache {event.get('cache_read', 0)} · out {event.get('output_tokens', 0)}[/dim]"
        )
    return render(event)   # 兜底:复用纯文本渲染