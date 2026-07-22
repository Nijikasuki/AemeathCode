"""TUI 前端的渲染:事件 → 带 Rich 行内标记的一行。

和 CLI 的 render() 是同一份事件的两种呈现:
  * CLI 用裸 print,不认识标记 → cli/render.py 出纯文本
  * TUI 的 Static 会解析标记   → 这里出富标记,同一行内可逐词着色

注:tool.* 事件由 ToolCallBlock 单独渲染,流式事件由 LLMStreamBlock 处理,
都不走这里。
"""


def event_markup(event: dict) -> str:
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

    # 兜底:没专门排版的事件类型,暗色显示一下类型名即可
    return f"[dim]{etype}[/dim]"
