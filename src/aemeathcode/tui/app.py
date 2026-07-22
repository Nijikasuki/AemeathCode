"""Aemeath 交互式 TUI 客户端 —— 编排层。

只干三件事:①连上 core ②把事件流分发成界面上的块 ③处理输入。
外观在 theme.py,组件在 widgets.py,事件文案在 render.py。

界面 = 顶部状态条 + 滚动日志区 + 底部输入框。
注意:每次回车都是一个【独立的 run】,不携带上一轮的对话历史
(跨轮会话记忆属于后续阶段)。
"""
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Label, Static

from aemeathcode.core.config import get_config
from aemeathcode.transport.socket_client import SocketClient
from aemeathcode.tui.render import event_markup
from aemeathcode.tui.theme import AEMEATH_THEME, APP_CSS, BANNER
from aemeathcode.tui.widgets import LLMStreamBlock, ToolCallBlock

# 流式增量事件(要拼接成一段),其余事件都是"一次成型的一行"
STREAM_TYPES = {"llm.thinking", "llm.token"}

# 不在 TUI 里显示的事件:run.started 的 goal 已经由输入回显过了,重复
HIDDEN_TYPES = {"run.started"}


def _elapsed_ms(start_iso: str | None, end_iso: str | None) -> int:
    """由两个事件的 ts 算出工具耗时。"""
    if not start_iso or not end_iso:
        return 0
    try:
        delta = datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)
        return max(int(delta.total_seconds() * 1000), 0)
    except ValueError:
        return 0


class AemeathApp(App):
    CSS = APP_CSS
    BINDINGS = [("ctrl+q", "quit", "退出")]

    def __init__(self) -> None:
        super().__init__()
        self._client: SocketClient | None = None
        self._block: LLMStreamBlock | None = None   # 当前活跃的流式块
        self._stream_type: str | None = None        # 当前在流哪一种
        # tool_use_id → (块, 开始时间);结果事件后到,靠它找回对应的块
        self._tools: dict[str, tuple[ToolCallBlock, str]] = {}

    def compose(self) -> ComposeResult:
        yield Label("[bold]AemeathCode[/bold]  [dim]connecting…[/dim]", id="status")
        yield VerticalScroll(id="log")
        yield Input(placeholder="输入目标，回车执行  ·  Ctrl+Q 退出", id="goal")

    def on_mount(self) -> None:
        self.register_theme(AEMEATH_THEME)
        self.theme = "aemeath"
        self.query_one("#log", VerticalScroll).mount(Static(BANNER, id="banner"))
        self.query_one("#goal", Input).focus()
        self.run_worker(self._connect)

    # ---- 小工具 ----

    def _set_status(self, markup: str) -> None:
        self.query_one("#status", Label).update(f"[bold]AemeathCode[/bold]  {markup}")

    def _end_block(self) -> None:
        """当前流式段落定格(触发 Markdown 重渲染)。"""
        if self._block is not None:
            self._block.finalize()
        self._block = None
        self._stream_type = None

    # ---- 连接与事件 ----

    async def _connect(self) -> None:
        config = get_config()
        view = self.query_one("#log", VerticalScroll)
        client = SocketClient(config.host, config.port)
        try:
            await client.connect()
        except OSError as e:
            self._set_status("[$error]disconnected[/$error]")
            await view.mount(Static(f"连不上 core ({config.host}:{config.port}): {e}", classes="sys"))
            await view.mount(Static("请先在另一个终端运行: aemeath core", classes="sys"))
            return

        client.on_event(self._on_event)
        self._client = client
        self._set_status(f"[dim]{config.host}:{config.port}[/dim]  [$success]ready[/$success]")
        # 常驻读循环:send_command 的响应正是靠它唤醒
        await client.run_event_loop()
        self._set_status("[$error]disconnected[/$error]")

    async def _on_event(self, event: dict) -> None:
        view = self.query_one("#log", VerticalScroll)
        etype = event.get("type")

        if etype in STREAM_TYPES:
            # 换段了(或刚开始)→ 上一段定格,新建一个块挂上去
            if self._block is None or self._stream_type != etype:
                self._end_block()
                thinking = etype == "llm.thinking"
                self._block = LLMStreamBlock(
                    markdown=not thinking,               # 只有回答需要 Markdown
                    classes="thinking" if thinking else "answer",
                )
                await view.mount(self._block)
                self._stream_type = etype
            # 累加+更新每个流式事件都要做,不能包进上面的 if
            self._block.append_token(event.get("content", ""))

        elif etype == "tool.call_started":
            self._end_block()
            block = ToolCallBlock(event.get("tool_name", ""), event.get("params", {}))
            self._tools[event.get("tool_use_id", "")] = (block, event.get("ts", ""))
            await view.mount(block)

        elif etype == "tool.call_finished":
            # 结果事件后到:按 tool_use_id 找回当初那个块,补写结果
            found = self._tools.pop(event.get("tool_use_id", ""), None)
            if found is not None:
                block, started_at = found
                block.set_result(
                    str(event.get("content", "")),
                    _elapsed_ms(started_at, event.get("ts")),
                    is_error=bool(event.get("is_error")),
                )

        else:
            self._end_block()
            if etype not in HIDDEN_TYPES:
                await view.mount(Static(event_markup(event), classes="event"))
            if etype == "run.completed":
                self._set_status("[dim]idle[/dim]")

        view.scroll_end(animate=False)

    # ---- 输入 ----

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        goal = event.value.strip()
        if not goal:
            return
        event.input.value = ""

        view = self.query_one("#log", VerticalScroll)
        await view.mount(Static(f"❯ {goal}", classes="user"))
        view.scroll_end(animate=False)

        if self._client is None:
            await view.mount(Static("尚未连接到 core，请检查 core 是否已启动。", classes="sys"))
            return

        self._end_block()
        self._set_status("[$accent]running…[/$accent]")
        await self._client.send_command("run", {"goal": goal})
        view.scroll_end(animate=False)


def run() -> None:
    AemeathApp().run()
