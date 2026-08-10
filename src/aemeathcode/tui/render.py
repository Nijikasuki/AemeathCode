"""事件 → 台账行的三段式(gutter 符号 / 内容 / 右侧 metric)。

和 CLI 的 render() 是同一份事件的两种呈现:
  * CLI 用裸 print,出纯文本
  * TUI 出台账行,由 ledger.py 负责排版

注:tool.* / llm.* / subagent.* 由各自的 widget 渲染,不走这里。

口吻规则(docs/design/identity.md §4):不用 emoji、不加句末标点、不用感叹号、
不自称、不问候、不道歉、不庆祝。状态词 2–4 个字。
"""
from rich.text import Text

from aemeathcode.tui.ledger import SYM
from aemeathcode.tui.theme import S_ERROR


def event_row(event: dict) -> tuple[str, Text, str]:
    """返回 (gutter 符号, 内容, metric)。"""
    etype = event.get("type", "")

    if etype == "run.completed":
        ok = event.get("status") == "success"
        if ok:
            # token 数不进这一行 —— 它是 debug metadata,归 /usage。
            # 旧版 `✓ success 3 步 · in 704 · cache 27776 · out 544` 是每轮屏幕上
            # 最显眼的一行,也是价值最低的一行。
            return SYM["done"], Text(f"{event.get('steps', 0)} 步", style="dim"), ""
        return SYM["error"], Text(str(event.get("error") or "失败"), style=S_ERROR), ""

    if etype == "context.compacted":
        before, after = event.get("before", 0), event.get("after", 0)
        return SYM["compact"], Text("context 已压缩", style="dim"), f"{before} → {after} 条"

    if etype == "context.compacting":
        return SYM["compact"], Text("正在压缩 context", style="dim"), SYM["busy"]

    return "", Text(etype, style="dim"), ""
