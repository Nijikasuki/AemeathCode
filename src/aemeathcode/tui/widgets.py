"""TUI 的组件层:每个 widget 自己持有状态、自己管自己的显示。

* LLMStreamBlock —— 一段流式文本(思考 / 回答)
* ToolCallBlock  —— 一次工具调用,可点击展开细节
"""
import json
from typing import Any

from rich.markdown import Markdown

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


def _preview(text: str, limit: int) -> str:
    text = str(text).replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


class LLMStreamBlock(Static):
    """一段流式文本 = 一个 widget。

    两阶段渲染:
      * 流的过程中 append_token → 纯文本整体替换(打字机,便宜)
      * 定格时 finalize() → 回答重渲染成 Markdown(表格 / 代码 / 粗体才好看)
    """

    def __init__(self, *, markdown: bool = False, classes: str | None = None) -> None:
        super().__init__("", classes=classes)
        self._text = ""
        self._markdown = markdown
        self._finalized = False

    def append_token(self, token: str) -> None:
        if self._finalized:
            return
        self._text += token          # ① 攒出完整文本
        self.update(self._text)      # ② 整体替换 = 打字机

    def finalize(self) -> None:
        """段落结束:回答块重渲染成 Markdown,思考块保持朴素。"""
        if self._finalized:
            return
        self._finalized = True
        if self._markdown and self._text.strip():
            self.update(Markdown(self._text, code_theme="monokai"))


class ToolCallBlock(Widget):
    """一次工具调用 = 一个可折叠 widget。

    折叠时只显示一行摘要;点击后展开完整参数与输出。
    结果是后到的(tool.call_finished),所以留了 set_result 供事后补写。
    """

    DEFAULT_CSS = """
    ToolCallBlock { height: auto; padding: 0 2; }
    ToolCallBlock > .detail {
        display: none;
        padding: 0 0 0 4;
        color: $text-muted;
    }
    ToolCallBlock.expanded > .detail { display: block; }
    """

    def __init__(self, tool_name: str, params: dict[str, Any]) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._params_full = json.dumps(params, ensure_ascii=False)
        self._output = ""
        self._elapsed_ms = 0
        self._is_error = False
        self._finished = False

    def compose(self) -> ComposeResult:
        yield Static(self._summary(), classes="summary")
        yield Static("", classes="detail")

    def _summary(self) -> str:
        line = (
            f"[dim]tool[/dim] [bold $secondary]{self._tool_name}[/bold $secondary]"
            f"  [dim]{_preview(self._params_full, 60)}[/dim]"
        )
        if self._finished:
            color, status = ("$error", "failed") if self._is_error else ("$success", "done")
            hint = "  [dim](点击展开)[/dim]" if self._output else ""
            line += (
                f"\n[dim]↳[/dim] [{color}]{status}[/{color}]"
                f"  [dim]{_preview(self._output, 70)}  {self._elapsed_ms}ms[/dim]{hint}"
            )
        return line

    def set_result(self, output: str, elapsed_ms: int, *, is_error: bool = False) -> None:
        self._output = output
        self._elapsed_ms = elapsed_ms
        self._is_error = is_error
        self._finished = True
        if self.children:                     # 还没挂载时跳过 DOM 更新
            self.query_one(".summary", Static).update(self._summary())

    def on_click(self) -> None:
        if not self._finished:
            return
        if "expanded" in self.classes:
            self.remove_class("expanded")
        else:
            self.query_one(".detail", Static).update(
                f"[dim]params:[/dim] {self._params_full}\n"
                f"[dim]output:[/dim] {self._output}"
            )
            self.add_class("expanded")
