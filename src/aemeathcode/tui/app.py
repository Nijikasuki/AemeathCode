"""Aemeath 交互式 TUI 客户端 —— 编排层。

只干三件事:①连上 core ②把事件流分发成界面上的块 ③处理输入。
外观在 theme.py,组件在 widgets.py,事件文案在 render.py。

界面 = 顶部状态条 + 滚动日志区 + 底部输入框。
注意:每次回车都是一个【独立的 run】,不携带上一轮的对话历史
(跨轮会话记忆属于后续阶段)。
"""
import asyncio
import json
import time
from datetime import datetime

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widgets import Collapsible, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from aemeathcode.core.compact.budget import context_window
from aemeathcode.core.config import get_config
from aemeathcode.transport.socket_client import SocketClient
from aemeathcode.tui.render import event_markup
from aemeathcode.tui.theme import AEMEATH_THEME, APP_CSS, BANNER
from aemeathcode.tui.widgets import CompactionIndicator, LLMStreamBlock, ToolCallBlock

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


class SessionPicker(ModalScreen[str | None]):
    """模态弹层:列出会话,↑↓ 选、Enter 返回选中的完整 session_id、Esc 取消返回 None。"""

    BINDINGS = [("escape", "dismiss_none", "取消")]

    DEFAULT_CSS = """
    SessionPicker {
        align: center middle;
    }
    SessionPicker #picker-box {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 80%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    SessionPicker #picker-title {
        margin-bottom: 1;
    }
    """

    def __init__(self, sessions: list) -> None:
        super().__init__()
        self._sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Label("选择要恢复的会话  ( ↑↓ 选择 · Enter 确认 · Esc 取消 )", id="picker-title")
            options = [
                Option(self._label(s), id=s.get("id"))
                for s in self._sessions
            ]
            yield OptionList(*options, id="picker-list")

    @staticmethod
    def _label(s: dict) -> str:
        updated = (s.get("updated_at") or "")[:19]
        title = s.get("title") or "(无标题)"
        short = (s.get("id") or "")[:8]
        return f"{title}    {updated}    {short}"

    def on_mount(self) -> None:
        self.query_one("#picker-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)   # 返回选中会话的完整 id

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class PermissionPrompt(Vertical):
    """内联权限请求:不覆盖整屏,直接嵌进对话流(#log)里,跟在那条工具调用下面,
    像 Claude Code。用户选完,resolve 传进来的 Future,再把自己从对话里移除。
    选项 id 就是 decision(allow_once/allow_always/deny);1/2/3 数字键 + ↑↓ Enter 都能选,Esc=deny。"""

    BINDINGS = [
        ("1", "pick('allow_once')", "允许一次"),
        ("2", "pick('allow_always')", "总是允许"),
        ("3", "pick('deny')", "拒绝"),
        ("escape", "pick('deny')", "拒绝"),
    ]

    DEFAULT_CSS = """
    PermissionPrompt {
        height: auto;
        border: round $warning;
        padding: 0 1;
        margin: 1 0;
    }
    PermissionPrompt #perm-head { color: $warning; }
    PermissionPrompt #perm-detail { color: $text-muted; margin-bottom: 1; }
    PermissionPrompt OptionList { height: auto; background: transparent; }
    """

    def __init__(self, ask: dict, future: "asyncio.Future[str]") -> None:
        super().__init__()
        self._ask = ask
        self._future = future

    def compose(self) -> ComposeResult:
        tool = self._ask.get("tool_name", "")
        detail = self._ask.get("detail", "")
        yield Label(f"⏵ 权限请求 · 工具 [bold]{tool}[/bold]", id="perm-head")
        yield Static(detail or "(无详情)", id="perm-detail")
        yield OptionList(
            Option("1. 允许一次", id="allow_once"),
            Option("2. 总是允许(记住,不再询问)", id="allow_always"),
            Option("3. 拒绝", id="deny"),
            id="perm-options",
        )

    def on_mount(self) -> None:
        self.query_one("#perm-options", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.action_pick(event.option.id)

    def action_pick(self, decision: str) -> None:
        if not self._future.done():
            self._future.set_result(decision)
        self.remove()   # 选完把自己从对话流里撤掉


class AemeathApp(App):
    CSS = APP_CSS
    BINDINGS = [("ctrl+q", "quit", "退出")]

    def __init__(self) -> None:
        super().__init__()
        self._client: SocketClient | None = None
        self._session_id: str | None = None         # 连上后 create 一次,之后每次 run 复用
        self._block: LLMStreamBlock | None = None   # 当前活跃的流式块
        self._stream_type: str | None = None        # 当前在流哪一种
        # tool_use_id → (块, 开始时间);结果事件后到,靠它找回对应的块
        self._tools: dict[str, tuple[ToolCallBlock, str]] = {}
        self._model: str = get_config().model                 # 顶部显示 + 查窗口用
        self._show_thinking: bool = get_config().show_thinking  # UI 是否显示 thinking(config 开关)
        self._window: int = context_window(self._model)       # 当前模型的上下文窗口
        self._status_markup: str = "[dim]connecting…[/dim]"  # 状态段(ready/running/idle…)
        self._ctx_used: int = 0                               # 当前水位条显示的 used(动画起点)
        self._pending_compaction: bool = False               # 刚压缩过?下一次水位更新走下降动画
        self._compaction_widget: CompactionIndicator | None = None  # 压缩进行中的指示器
        self._ctx_markup: str = self._ctx_bar(0, self._window)  # 水位段,一开始就是 0%
        self._top_run_id = None
        # 子 agent 嵌套渲染:spawn 的 tool_use_id → 折叠块;子 run_id → 折叠块(subagent.started 建立)
        self._spawn_blocks: dict[str, Collapsible] = {}
        self._sub_containers: dict[str, Collapsible] = {}
        self._sess_in = self._sess_out = self._sess_cache = 0   # 本会话累计 token(状态栏右侧)
        self._run_start: float | None = None                    # 顶层 run 开始时刻(monotonic),None=不在跑
        self._running_subs: dict[Collapsible, float] = {}        # 正在跑的子 agent 折叠块 → 开始时刻

    def compose(self) -> ComposeResult:
        yield Label("[bold]AemeathCode[/bold]  [dim]connecting…[/dim]", id="status")
        yield VerticalScroll(id="log")
        yield Input(
            placeholder="输入目标回车执行  ·  / 命令(灰字提示,→ 补全)  ·  Ctrl+Q 退出",
            id="goal",
            suggester=SuggestFromList(["/sessions", "/resume", "/clear", "/usage", "/exit"], case_sensitive=False),
        )

    def on_mount(self) -> None:
        self.register_theme(AEMEATH_THEME)
        self.theme = "aemeath"
        self.query_one("#log", VerticalScroll).mount(Static(BANNER, id="banner"))
        self.query_one("#goal", Input).focus()
        self.run_worker(self._connect)
        self.set_interval(1.0, self._tick)   # 每秒刷新运行中计时器(主 run + 子 agent)

    # ---- 小工具 ----

    def _render_status(self) -> None:
        line = f"[bold]AemeathCode[/bold]  [dim]{self._model}[/dim]  {self._status_markup}"
        if self._ctx_markup:
            line += f"   {self._ctx_markup}"
        line += (f"   [dim]Σ {self._fmt_tokens(self._sess_in)}↑ "
                 f"{self._fmt_tokens(self._sess_out)}↓ ⚡{self._fmt_tokens(self._sess_cache)}[/dim]")   # 累计 in↑/out↓/cache命中⚡(含子 agent)
        self.query_one("#status", Label).update(line)

    def _set_status(self, markup: str) -> None:
        self._status_markup = markup
        self._render_status()

    def _set_ctx(self, markup: str) -> None:
        self._ctx_markup = markup
        self._render_status()

    def _tick(self) -> None:
        """每秒跑一次:给正在运行的主 run / 子 agent 更新"已跑 N 秒"。都不在跑时啥也不做。"""
        now = time.monotonic()
        if self._run_start is not None:
            self._set_status(f"[$accent]running… {int(now - self._run_start)}s[/$accent]")
        for collapsible, start in self._running_subs.items():
            base = getattr(collapsible, "_base_title", "🤖 子 agent")
            collapsible.title = f"{base} · 运行中 {int(now - start)}s"

    @staticmethod
    def _fmt_tokens(n: int) -> str:
        """token 数变人话:1_180_000→1.2M,118_000→118k,3200→3.2k,500→500。"""
        if n >= 1_000_000:
            return f"{n / 1e6:.1f}M"
        if n >= 1_000:
            return f"{n / 1e3:.1f}k" if n < 10_000 else f"{n / 1e3:.0f}k"
        return str(n)

    @classmethod
    def _ctx_bar(cls, used: int, window: int) -> str:
        """把水位 used/window 渲染成一根 10 格进度条 + 百分比 + 绝对 token 数,按占比变色。
        1M 窗口下真实占用常不足 1%,光看百分比像没动,所以带上绝对值(如 9.0k/1M)。"""
        pct = used / window if window else 0.0
        pct = max(0.0, min(pct, 1.0))
        filled = round(pct * 10)
        bar = "▓" * filled + "░" * (10 - filled)
        color = "$success" if pct < 0.6 else ("$warning" if pct < 0.85 else "$error")
        return (
            f"[dim]ctx[/dim] [{color}]{bar}[/{color}] "
            f"[{color}]{pct * 100:.0f}%[/{color}] "
            f"[dim]{cls._fmt_tokens(used)}/{cls._fmt_tokens(window)}[/dim]"
        )

    def _show_ctx(self, used: int) -> None:
        """瞬时更新水位条(记住当前值,给动画当起点)。"""
        self._ctx_used = used
        self._set_ctx(self._ctx_bar(used, self._window))

    def _remove_compaction_widget(self) -> None:
        if self._compaction_widget is not None:
            self._compaction_widget.remove()
            self._compaction_widget = None

    def _animate_ctx_to(self, target: int) -> None:
        """压缩后水位下降:从当前值分帧滑到 target(~0.7s),让"掉下去"看得见。"""
        start = self._ctx_used
        if start == target:
            self._show_ctx(target)
            return
        steps = 12
        self._anim_step = 0

        def tick() -> None:
            self._anim_step += 1
            cur = round(start + (target - start) * self._anim_step / steps)
            self._show_ctx(cur)

        self.set_interval(0.06, tick, repeat=steps)   # 12 帧 × 0.06s ≈ 0.7s,跑完自动停

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
        client.on_ask(self._prompt_permission)
        self._client = client

        # 读循环必须【先】并发跑起来:send_command 的响应正是靠它读到再唤醒 Future。
        # 所以把它丢到后台 worker,而不是在这一行阻塞等它。
        self.run_worker(self._read_loop)

        # 现在有人在读了 → 才能发 session.create 并 await 到它的响应。
        try:
            resp = await client.send_command("session.create", {})
            self._session_id = resp["session_id"]
        except Exception as e:  # noqa: BLE001
            self._set_status("[$error]session 创建失败[/$error]")
            await view.mount(Static(f"创建会话失败: {e}", classes="sys"))
            return

        self._set_status(
            f"[dim]{config.host}:{config.port}[/dim]  [$success]ready[/$success]  "
            f"[dim]session {self._session_id[:8]}[/dim]"
        )

    async def _read_loop(self) -> None:
        """常驻读循环单独占一个 worker:与 send_command 并发,负责读响应/派发事件。"""
        assert self._client is not None
        await self._client.run_event_loop()
        self._set_status("[$error]disconnected[/$error]")

    def _container_for(self, event: dict):
        """按事件的 run_id 决定 mount 到哪:子 agent 的事件进它折叠块的 body(嵌套缩进),否则进主日志。"""
        collapsible = self._sub_containers.get(event.get("run_id"))
        if collapsible is not None:
            return collapsible.query_one(Collapsible.Contents)
        return self.query_one("#log", VerticalScroll)

    async def _on_event(self, event: dict) -> None:
        etype = event.get("type")

        # 水位事件:只更新顶部状态条,不往日志区刷屏(它每轮都来)
        if etype == "context.usage":
            self._window = event.get("window", self._window)   # 以 daemon 的窗口为准
            used = event.get("used", 0)
            if self._pending_compaction:
                self._pending_compaction = False
                self._animate_ctx_to(used)                     # 刚压缩过 → 平滑下降,看得见
            else:
                self._show_ctx(used)                           # 平时瞬时更新
            return

        # 链接事件:纯粹给父子建映射,不渲染成行。用 parent_tool_use_id 找到 spawn 折叠块,
        # 记下"这个子 run_id 的事件都往那个块里塞"。
        if etype == "subagent.started":
            collapsible = self._spawn_blocks.get(event.get("parent_tool_use_id"))
            if collapsible is not None:
                self._sub_containers[event.get("run_id")] = collapsible
            return

        # thinking 显示开关:关了就直接丢掉 thinking 事件(daemon 照常发,只是 UI 不画)
        if etype == "llm.thinking" and not self._show_thinking:
            return

        log = self.query_one("#log", VerticalScroll)   # 滚动始终针对主日志
        container = self._container_for(event)          # mount 目标:子事件进折叠块,否则主日志

        if etype in STREAM_TYPES:
            # 换段了(或刚开始)→ 上一段定格,新建一个块挂上去
            if self._block is None or self._stream_type != etype:
                self._end_block()
                thinking = etype == "llm.thinking"
                self._block = LLMStreamBlock(
                    markdown=not thinking,               # 只有回答需要 Markdown
                    classes="thinking" if thinking else "answer",
                )
                await container.mount(self._block)
                self._stream_type = etype
            # 累加+更新每个流式事件都要做,不能包进上面的 if
            self._block.append_token(event.get("content", ""))

        elif etype == "tool.call_started":
            self._end_block()
            if event.get("tool_name") == "spawn_agent":
                # 子 agent:建一个可折叠块,它的所有事件之后都塞进这个块的 body(嵌套)
                goal = str(event.get("params", {}).get("goal", ""))[:40]
                base = f"🤖 子 agent · {goal}…"
                collapsible = Collapsible(title=f"{base} · 运行中", collapsed=False, classes="subagent")
                collapsible._spawn_start_ts = event.get("ts", "")   # 记开始时刻(ISO),子跑完算最终耗时
                collapsible._base_title = base                       # 计时器每秒重写标题时用
                self._spawn_blocks[event.get("tool_use_id", "")] = collapsible
                self._running_subs[collapsible] = time.monotonic()   # 加入运行中计时
                await container.mount(collapsible)
            else:
                block = ToolCallBlock(event.get("tool_name", ""), event.get("params", {}))
                self._tools[event.get("tool_use_id", "")] = (block, event.get("ts", ""))
                await container.mount(block)

        elif etype == "tool.call_finished":
            tuid = event.get("tool_use_id", "")
            if tuid in self._spawn_blocks:
                # 子 agent 结束:折叠(子 transcript 收起,不与父转述重复)。
                # 标题的"完成 · N步 · token · 耗时"由子的 run.completed 更新(见下方 else 分支);
                # 这里只兜底:万一子没正常发 run.completed,别让标题永远停在"运行中"
                collapsible = self._spawn_blocks[tuid]
                if collapsible.title.endswith("运行中"):
                    collapsible.title = "✓ 子 agent 完成"
                collapsible.collapsed = True
            else:
                # 普通工具:按 tool_use_id 找回当初那个块,补写结果
                found = self._tools.pop(tuid, None)
                if found is not None:
                    block, started_at = found
                    block.set_result(
                        str(event.get("content", "")),
                        _elapsed_ms(started_at, event.get("ts")),
                        is_error=bool(event.get("is_error")),
                    )

        elif etype == "context.compacting":
            # 压缩开始:挂一个"正在压缩"指示器(脉冲条),压完再撤
            self._end_block()
            self._compaction_widget = CompactionIndicator()
            await container.mount(self._compaction_widget)

        elif etype == "context.compacted":
            # 压缩完成:撤掉指示器,留下一行结果,并让下一次水位更新走下降动画
            self._end_block()
            self._remove_compaction_widget()
            await container.mount(Static(event_markup(event), classes="event"))
            self._pending_compaction = True

        else:
            self._end_block()
            if etype not in HIDDEN_TYPES:
                await container.mount(Static(event_markup(event), classes="event"))
            if etype == "run.completed":
                rid = event.get("run_id")
                if rid in self._sub_containers:
                    # 子 agent 完成:把 步数 / token / 耗时 写进它折叠块的标题
                    collapsible = self._sub_containers[rid]
                    elapsed = _elapsed_ms(getattr(collapsible, "_spawn_start_ts", ""), event.get("ts"))
                    collapsible.title = (
                        f"✓ 子 agent · {event.get('steps', 0)} 步 · "
                        f"in {event.get('input_tokens', 0)} · out {event.get('output_tokens', 0)} · {elapsed}ms"
                    )
                    self._running_subs.pop(collapsible, None)   # 停子 agent 计时
                elif rid == self._top_run_id:
                    self._run_start = None                      # 停主 run 计时
                    self._remove_compaction_widget()   # 兜底:压缩若异常中断,别让指示器卡住
                    self._set_status("[dim]idle[/dim]")
                    # 会话累计 token:每个顶层 run 的总量(2b 修复后已含子 agent)累加 → 状态栏
                    self._sess_in += event.get("input_tokens", 0)
                    self._sess_out += event.get("output_tokens", 0)
                    self._sess_cache += event.get("cache_read", 0)
                    self._render_status()

        log.scroll_end(animate=False)


    async def _prompt_permission(self, ask: dict) -> str:
        # 内联:往对话区挂一个 PermissionPrompt(不覆盖整屏),await Future 等它被选中。
        # 选中后 prompt 自己 set_result + remove;这里拿到 decision,顺手把焦点还给输入框。
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        view = self.query_one("#log", VerticalScroll)
        await view.mount(PermissionPrompt(ask, future))
        view.scroll_end(animate=False)
        try:
            return await future
        finally:
            self.query_one("#goal", Input).focus()
    # ---- 输入 ----

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        view = self.query_one("#log", VerticalScroll)

        if self._client is None:
            await view.mount(Static("尚未连接到 core，请检查 core 是否已启动。", classes="sys"))
            return

        # 斜杠命令:分流,不当 goal 发出去
        if text.startswith("/"):
            await self._handle_command(text, view)
            return

        await view.mount(Static(f"❯ {text}", classes="user"))
        view.scroll_end(animate=False)

        if self._session_id is None:
            await view.mount(Static("会话尚未就绪，请稍候…", classes="sys"))
            return

        self._end_block()
        self._set_status("[$accent]running…[/$accent]")
        ack = await self._client.send_command("run", {"goal": text, "session_id": self._session_id})
        self._top_run_id = ack.get("run_id")
        self._run_start = time.monotonic()   # 开始主 run 计时
        view.scroll_end(animate=False)

    # ---- 斜杠命令(跟 CLI chat 同一套:检测 → 调对应 session.* 命令)----

    async def _handle_command(self, text: str, view: VerticalScroll) -> None:
        if text == "/sessions":
            resp = await self._client.send_command("session.list", {})
            await self._show_sessions(resp["sessions"], view)
        elif text == "/usage":
            resp = await self._client.send_command("session.usage", {"session_id": self._session_id})
            if isinstance(resp, str):
                await view.mount(Static(resp, classes="sys"))
            else:
                await view.mount(Static(
                    f"📊 本会话累计 token:输入 {resp['input_tokens']} · "
                    f"输出 {resp['output_tokens']} · 缓存读 {resp['cache_read']}",
                    classes="sys"))
        elif text == "/clear":
            created = await self._client.send_command("session.create", {"mode": "multi_turn"})
            self._session_id = created["session_id"]
            await view.remove_children()
            self._show_ctx(0)   # 新会话上下文清零 → 0%
            self._sess_in = self._sess_out = self._sess_cache = 0   # 会话累计 token 归零
            self._spawn_blocks.clear(); self._sub_containers.clear()   # 折叠块映射清干净,别留悬空引用
            self._run_start = None; self._running_subs.clear()   # 计时器归零
            self._render_status()
            await view.mount(Static(f"🧹 已开新会话 (session={self._session_id[:8]})", classes="sys"))
        elif text.startswith("/resume"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:                       # /resume <id>:直接恢复
                await self._do_resume(parts[1].strip(), view)
            else:                                     # /resume:弹选择器(在 worker 里跑)
                self._pick_and_resume(view)
        else:
            await view.mount(Static(f"未知命令:{text}  (可用 /sessions /resume /clear)", classes="sys"))
        view.scroll_end(animate=False)

    @work
    async def _pick_and_resume(self, view: VerticalScroll) -> None:
        # push_screen_wait 会挂起等弹层关闭,必须在 worker 里跑,否则堵住消息泵
        resp = await self._client.send_command("session.list", {})
        sessions = resp["sessions"]
        if not sessions:
            await view.mount(Static("(还没有历史会话)", classes="sys"))
            return
        target = await self.push_screen_wait(SessionPicker(sessions))
        if target:                                    # None = Esc 取消
            await self._do_resume(target, view)

    async def _do_resume(self, target: str, view: VerticalScroll) -> None:
        resp = await self._client.send_command("session.resume", {"session_id": target})
        if isinstance(resp, str):      # handler 用字符串报错(如"会话不存在")
            await view.mount(Static(resp, classes="sys"))
            return
        self._session_id = resp["session_id"]
        await view.remove_children()
        self._spawn_blocks.clear(); self._sub_containers.clear()
        # 恢复会话:拉一次累计 usage 填状态栏(历史 run 的 token 总量)
        usage = await self._client.send_command("session.usage", {"session_id": self._session_id})
        if not isinstance(usage, str):
            self._sess_in = usage.get("input_tokens", 0)
            self._sess_out = usage.get("output_tokens", 0)
            self._sess_cache = usage.get("cache_read", 0)
            self._render_status()
        # resume 还没发问 → 没有实时 usage,先用历史本地估一把水位(问第一句后被真实值刷新)
        used = sum(_estimate_msg_tokens(m) for m in resp["history"])
        self._show_ctx(used)
        title = resp.get("title") or ""
        await view.mount(Static(f"⏪ 已恢复会话 (session={self._session_id[:8]}  {title})", classes="sys"))
        await self._replay_history(resp["history"], view)

    async def _show_sessions(self, sessions: list, view: VerticalScroll) -> None:
        if not sessions:
            await view.mount(Static("(还没有历史会话)", classes="sys"))
            return
        lines = ["历史会话(最近在前):"]
        for s in sessions:
            updated = (s.get("updated_at") or "")[:19]
            title = s.get("title") or "(无标题)"
            lines.append(f"  {s.get('id')}  {updated}  {title}")   # 完整 id,方便复制去 /resume
        await view.mount(Static("\n".join(lines), classes="sys"))

    async def _replay_history(self, history: list, view: VerticalScroll) -> None:
        for msg in history:
            content = _extract_text(msg.get("content"))
            if not content.strip():
                continue   # 跳过纯 tool 块的消息
            if msg.get("role") == "user":
                await view.mount(Static(f"❯ {content}", classes="user"))
            else:
                # 用跟 live 回答同款的块渲染 markdown,观感一致(粗体/列表/分隔线才好看)
                block = LLMStreamBlock(markdown=True, classes="answer")
                await view.mount(block)
                block.append_token(content)
                block.finalize()


def _estimate_msg_tokens(msg: dict) -> int:
    """resume 时本地粗估一条消息的 token(chars/4),和 compactor 同款启发式。
    只用于展示近似水位,真实值由第一轮 chat 的 usage 事件刷新。"""
    content = msg.get("content")
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return len(text) // 4


def _extract_text(content) -> str:
    """从一条 message 的 content 抽可读文本:str 直接用;list 取 text 块。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def run() -> None:
    AemeathApp().run()
