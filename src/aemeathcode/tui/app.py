"""Aemeath 交互式 TUI 客户端 —— 编排层。

只干三件事:①连上 core ②把事件流分发到各个面板 ③处理输入。
面板在 panels.py,content 区的行渲染在 widgets.py / ledger.py,外观在 theme.py。

布局(lazygit 式的多区域,不是聊天窗口):

    ┌ Status ────┐┌ Content ─────────────────────┐
    │            ││                              │
    ├ Tasks ─────┤│   LOGO / 对话 / 工具活动      │
    │            ││                              │
    ├ Thinking ──┤│                              │
    │            ││                              │
    ├ Sessions ──┤└──────────────────────────────┘
    │            │┌ › ───────────────────────────┐
    └────────────┘└──────────────────────────────┘
     ^p/^n 选会话 · ^u/^d 滚动 · /resume · ^q 退出            ░ 4%

从 lazygit 学来的三条原则、以及为什么它们对 coding agent 成立,见 panels.py 的模块 docstring。
最关键的一手是**把 thinking 拎成独立面板** —— 它一直可见,但物理上淹不了正文。

输入是**常驻直接打字**(不是 lazygit 的模式化导航),代价是单键留给输入,
导航走斜杠命令和 Ctrl 组合键。对 agent 来说随手能打字比 vim 手感更重要。
"""
import asyncio
import json
import os
import time
from datetime import datetime

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.suggester import SuggestFromList
from textual.widget import Widget
from textual.widgets import Input, Static

from aemeathcode.core.compact.budget import context_window
from aemeathcode.core.config import get_config
from aemeathcode.transport.socket_client import SocketClient
from aemeathcode.tui import splash
from aemeathcode.tui.ledger import RULE, RULE_NESTED, SYM, LedgerFrame, LedgerRow, fit
from aemeathcode.tui.panels import (
    ApprovalPane,
    McpPanel,
    SessionsPanel,
    SkillsPanel,
    StatusPanel,
    TasksPanel,
    ThinkingPanel,
)
from aemeathcode.tui.render import event_row
from aemeathcode.tui.theme import (
    AEMEATH_THEME,
    APP_CSS,
    S_ERROR,
    S_MOTION,
    S_STRUCT,
    S_WARN,
)
from aemeathcode.tui.widgets import (
    AnswerBlock,
    EventRow,
    SubagentBlock,
    ToolCall,
    ToolGroup,
    ToolRow,
    is_readonly,
)

HIDDEN_TYPES = {"run.started"}      # goal 已经由输入回显过了,重复
# /sessions 删掉了:Sessions 面板常驻可见,它没有任何 /resume 之外的作用
COMMANDS = ["/resume", "/clear", "/usage", "/mcp", "/about", "/help", "/exit"]
VERSION = "v0.2.1"
# identity 决策 3 原文是"≤1 帧"—— 但实测 60ms 作用在角落一个三字标签上,人眼来不及,
# 等于没做。130ms 仍然只是"闪一下"、不构成动画,但确实看得见。
SHEEN_STEP = 0.08   # logo 流光的帧间隔(~12fps),只在空态跑
HINTS = "^↑/^↓ 选会话 · Enter 恢复 · ^u/^d 滚动 content · ^j/^k 滚动 thinking · ^q 退出"


def _elapsed_ms(start_iso: str | None, end_iso: str | None) -> int:
    if not start_iso or not end_iso:
        return 0
    try:
        delta = datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)
        return max(int(delta.total_seconds() * 1000), 0)
    except ValueError:
        return 0


class AemeathApp(App):
    CSS = APP_CSS
    # Textual 自带 ctrl+p = 命令面板,会把我们的绑定吃掉,直接关掉
    ENABLE_COMMAND_PALETTE = False
    # priority=True 是必须的:焦点在 Input 上,而 Input 自己绑了 ctrl+u(删到行首)、
    # ctrl+k(删到行尾)。按键沿焦点链冒泡,App 在最末端,不给优先级就永远收不到。
    BINDINGS = [  # noqa: RUF012 —— Textual 的类属性约定
        Binding("ctrl+q", "quit", "退出", priority=True),
        Binding("ctrl+up", "session_prev", "上一个会话", priority=True),
        Binding("ctrl+down", "session_next", "下一个会话", priority=True),
        Binding("ctrl+u", "scroll_up", "content 上滚", priority=True),
        Binding("ctrl+d", "scroll_down", "content 下滚", priority=True),
        Binding("ctrl+k", "think_up", "thinking 上滚", priority=True),
        Binding("ctrl+j", "think_down", "thinking 下滚", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._client: SocketClient | None = None
        self._connected = False      # 读循环活着才为 True(P1-1:断连后别再 await 永久挂起)
        self._session_id: str | None = None
        self._model: str = get_config().model
        self._show_thinking: bool = get_config().show_thinking
        self._window: int = context_window(self._model)
        self._ctx_used = 0
        self._state = "connecting"
        # 左侧四个房间
        self.p_status = StatusPanel()
        self.p_tasks = TasksPanel()
        self.p_thinking = ThinkingPanel()
        self.p_sessions = SessionsPanel()
        self.p_mcp = McpPanel()
        self.p_skills = SkillsPanel()
        self.approval = ApprovalPane()
        # content 区的流式块
        self._answer: AnswerBlock | None = None
        self._streaming = False
        self._splash: Static | None = None
        self._splash_variant = "full"
        # tool 分组
        self._group: ToolGroup | None = None
        self._group_started = 0.0
        self._calls: dict[str, tuple[ToolCall, Widget]] = {}
        self._last_call: tuple[str, dict] = ("", {})
        # subagent 嵌套
        self._spawns: dict[str, SubagentBlock] = {}
        self._sub_runs: dict[str, SubagentBlock] = {}
        # run 计时
        self._top_run_id: str | None = None
        self._run_start: float | None = None
        self._phase = 0.0            # logo 流光的相位
        self._pending_perm: asyncio.Future[str] | None = None

    # ---- 布局 ----

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            with Vertical(id="side"):
                yield self.p_status
                yield self.p_sessions
                yield self.p_thinking
            with Vertical(id="main"):
                with Vertical(id="content", classes="panel"):
                    yield VerticalScroll(id="content-body")
                    yield self.approval
                with Horizontal(id="input-panel", classes="panel"):
                    yield Input(
                        placeholder="输入目标回车执行  ·  / 命令",
                        id="goal",
                        suggester=SuggestFromList(COMMANDS, case_sensitive=False),
                    )
            with Vertical(id="aside"):
                yield self.p_tasks
                yield self.p_mcp
                yield self.p_skills
        yield Static(Text(HINTS, style=S_STRUCT), id="hints")

    def on_mount(self) -> None:
        self.register_theme(AEMEATH_THEME)
        self.theme = "aemeath"
        content = self.query_one("#content", Vertical)
        content.border_title = "Content"
        content.border_subtitle = VERSION
        self.query_one("#input-panel", Horizontal).border_title = "›"
        # 每个房间开局就有内容,不留黑洞
        self.p_tasks.refresh_view()
        self.p_mcp.refresh_view()
        self.p_skills.refresh_view()
        self.p_thinking.clear()
        self.p_sessions.refresh_view()
        self._refresh_status()
        self._mount_splash()
        self.query_one("#goal", Input).focus()
        self.run_worker(self._connect)
        self.set_interval(1.0, self._tick)
        self.set_interval(SHEEN_STEP, self._sheen)

    # ---- 面板刷新 ----

    def _refresh_status(self) -> None:
        self.p_status.render_status(
            cwd=os.path.basename(os.getcwd()) or os.getcwd(),
            model=self._model or "",
            state=self._state_label(),
            session=self._session_id or "",
        )
        self.query_one("#hints", Static).update(self._hints_line())

    def _state_label(self) -> str:
        if self._state == "running" and self._run_start is not None:
            return f"running {int(time.monotonic() - self._run_start)}s"
        label = {
            "connecting": "连接中", "ready": "就绪", "idle": "就绪",
            "ask": "等待授权", "disconnected": "disconnected", "failed": "失败",
        }.get(self._state, self._state)
        return label

    def _hints_line(self) -> Text:
        """底部常驻契约行 —— lazygit 的可发现性来源:永远知道能按什么。

"""
        pct = self._ctx_used / self._window if self._window else 0.0
        bar = "▓" if pct >= 0.85 else ("▒" if pct >= 0.60 else "░")
        line = Text(HINTS, style=S_STRUCT)
        line.append(f"    {bar} {pct * 100:.0f}%", style=S_WARN if pct >= 0.6 else S_STRUCT)
        return line

    def _set_state(self, state: str) -> None:
        self._state = state
        self._refresh_status()

    def _tick(self) -> None:
        if self._state == "running":
            self._refresh_status()

    def _mount_splash(self) -> None:
        name = os.environ.get("AEMEATH_SPLASH", "full")
        if name == "none":
            return
        self._splash_variant = name
        self._phase = 0.0
        self._splash = Static(splash.make(name, self._phase), id="splash")
        self._view.mount(self._splash)

    def _sheen(self) -> None:
        """推进 logo 流光。只在空态存在时跑 —— 没有 logo 就不烧 CPU。

        这是 identity.md「有心跳的机器 / 波动爱心」那条:持续、周期、柔和的脉冲。
        """
        if self._splash is None or not self._splash.is_mounted:
            return
        self._phase += SHEEN_STEP
        self._splash.update(splash.make(self._splash_variant, self._phase))

    # ---- content 区 ----

    @property
    def _view(self) -> VerticalScroll:
        return self.query_one("#content-body", VerticalScroll)

    def _mount(self, container: Widget, widget: Widget):
        return container.mount(widget)

    def _container_for(self, event: dict) -> tuple[Widget, str]:
        """按 run_id 决定往哪挂:子 agent 的事件进它的 body(嵌套 + 换竖线字符)。"""
        block = self._sub_runs.get(event.get("run_id"))
        if block is not None:
            return block.body, RULE_NESTED
        return self._view, RULE

    def _close_group(self) -> None:
        if self._group is not None:
            self._group.close(int((time.monotonic() - self._group_started) * 1000))
            self._group = None

    def _end_answer(self) -> None:
        if self._answer is not None:
            self._answer.finalize()
            self._answer = None
        self._streaming = False

    # ---- 连接 ----

    async def _connect(self) -> None:
        config = get_config()
        client = SocketClient(config.host, config.port)
        try:
            await client.connect()
        except OSError as e:
            self._set_state("disconnected")
            await self._view.mount(EventRow(SYM["error"], Text(str(e), style=S_ERROR)))
            await self._view.mount(EventRow("", Text("重连: aemeath core", style="dim")))
            return

        client.on_event(self._on_event)
        client.on_ask(self._prompt_permission)
        self._client = client
        self._connected = True
        # 读循环必须【先】并发跑起来:send_command 的响应正是靠它读到再唤醒 Future
        self.run_worker(self._read_loop)
        try:
            resp = await client.send_command("session.create", {})
            self._session_id = resp["session_id"]
        except Exception as e:  # noqa: BLE001
            self._set_state("failed")
            await self._view.mount(EventRow(SYM["error"], Text(str(e), style=S_ERROR)))
            return
        self._set_state("ready")
        await self._load_sessions()
        await self._load_mcp()

    async def _read_loop(self) -> None:
        assert self._client is not None
        await self._client.run_event_loop()
        # P1-1:读循环一死就置断连标志。否则 send_command 照样挂 Future 并 await,
        # 而唯一能 resolve 它的读路径已经没了 → 永久挂起。
        self._connected = False
        self._set_state("disconnected")
        await self._view.mount(
            EventRow(SYM["error"], Text("core 已断开。重连: aemeath core", style=S_ERROR))
        )
        self._view.scroll_end(animate=False)

    async def _load_mcp(self) -> None:
        if self._client is None:
            return
        try:
            resp = await self._client.send_command("mcp.list", {})
        except Exception:  # noqa: BLE001
            return
        self.p_mcp.load(resp.get("servers", []))

    async def _load_sessions(self) -> None:
        if self._client is None:
            return
        try:
            resp = await self._client.send_command("session.list", {})
        except Exception:  # noqa: BLE001
            return
        self.p_sessions.load(resp.get("sessions", []))

    # ---- 事件分发 ----

    async def _on_event(self, event: dict) -> None:
        etype = event.get("type")

        if etype == "context.usage":
            self._window = event.get("window", self._window)
            self._ctx_used = event.get("used", 0)
            self._refresh_status()
            return

        if etype == "subagent.started":
            block = self._spawns.get(event.get("parent_tool_use_id"))
            if block is not None:
                self._sub_runs[event.get("run_id")] = block
            return

        # thinking 进它自己的房间,不进 content —— 这是整套布局最关键的一条:
        # 它一直可见,但物理上淹不了正文
        if etype == "llm.thinking":
            if self._show_thinking:
                self.p_thinking.append(event.get("content", ""))
            return

        container, rule = self._container_for(event)

        if etype == "llm.token":
            await self._on_answer(event, container, rule)
        elif etype == "tool.call_started":
            await self._on_tool_start(event, container, rule)
        elif etype == "tool.call_finished":
            self._on_tool_finish(event)
        elif etype in ("context.compacting", "context.compacted"):
            self._end_answer()
            sym, text, metric = event_row(event)
            await container.mount(EventRow(sym, text, metric, rule_char=rule))
        elif etype == "run.completed":
            await self._on_run_completed(event, container, rule)
        elif etype not in HIDDEN_TYPES:
            self._end_answer()
            sym, text, metric = event_row(event)
            await container.mount(EventRow(sym, text, metric, rule_char=rule))

        self._view.scroll_end(animate=False)

    async def _on_answer(self, event: dict, container: Widget, rule: str) -> None:
        self._close_group()
        if self._answer is None or not self._streaming:
            self._answer = AnswerBlock(rule_char=rule)
            await container.mount(self._answer)
        self._answer.append_token(event.get("content", ""))
        self._streaming = True

    async def _on_tool_start(self, event: dict, container: Widget, rule: str) -> None:
        # 后面跟了 tool call → 刚才那段文字是**过程叙述**不是最终回答 → 压暗
        if self._answer is not None:
            self._answer.finalize()
            self._answer.demote()
            self._answer = None
        self._streaming = False
        self.p_thinking.mark_segment()

        name = event.get("tool_name", "")
        params = event.get("params", {}) or {}
        tuid = event.get("tool_use_id", "")
        ts = event.get("ts", "")

        # 任务板从工具参数里就地推导 —— daemon 没有 task.* 的 RPC,事件流里信息已经够了
        if self.p_tasks.on_tool(name, params):
            self.p_tasks.refresh_view()
        if name == "use_skill":
            self.p_skills.used(str(params.get("name", "")))

        self._last_call = (name, params)   # 审批预览要拿它显示"将要写入什么"
        if name == "spawn_agent":
            self._close_group()
            block = SubagentBlock(fit(str(params.get("goal", "")), 48))
            block._started_at = ts
            self._spawns[tuid] = block
            await container.mount(block)
            return

        call = ToolCall(name=name, params=params, started_at=ts)
        if is_readonly(name):
            if self._group is None:
                self._group = ToolGroup(rule_char=rule)
                self._group_started = time.monotonic()
                await container.mount(self._group)
            self._group.add(call)
            self._calls[tuid] = (call, self._group)
        else:
            self._close_group()
            row = ToolRow(call, rule_char=rule)
            await container.mount(row)
            self._calls[tuid] = (call, row)

    def _on_tool_finish(self, event: dict) -> None:
        tuid = event.get("tool_use_id", "")
        if tuid in self._spawns:
            return   # 子 agent 的收尾由它自己的 run.completed 处理
        found = self._calls.pop(tuid, None)
        if found is None:
            return
        call, holder = found
        call.output = str(event.get("content", ""))
        call.elapsed_ms = _elapsed_ms(call.started_at, event.get("ts"))
        call.is_error = bool(event.get("is_error"))
        call.finished = True
        holder._repaint()

    async def _on_run_completed(self, event: dict, container: Widget, rule: str) -> None:
        self._end_answer()
        rid = event.get("run_id")
        if rid in self._sub_runs:
            block = self._sub_runs[rid]
            block.finish(event.get("steps", 0),
                         _elapsed_ms(getattr(block, "_started_at", ""), event.get("ts")))
            return

        self._close_group()
        if rid != self._top_run_id:
            return
        elapsed = time.monotonic() - self._run_start if self._run_start else 0.0
        self._run_start = None
        sym, text, metric = event_row(event)
        if event.get("status") == "success":
            text.append(f" · {elapsed:.1f}s", style="dim")   # 事实 + 代价,没有情绪
            self._set_state("idle")
        else:
            self._set_state("failed")
        await container.mount(EventRow(sym, text, metric, rule_char=rule))
        # 【死锁警告】绝对不能在这里 await send_command:_on_event 是被读循环的 _dispatch
        # 直接 await 的,而 send_command 要等的响应只能由那条读循环送达 —— 在读循环里
        # 等读循环 = 永久挂起,之后所有事件(thinking / content / 权限 ask)全部进不来。
        # 一律丢到独立 worker 里发。
        self.run_worker(self._load_sessions())

    # ---- 权限 ----

    async def _prompt_permission(self, ask: dict) -> str:
        """审批 —— 详情面板只在这一刻出现,批完就消失。

        不需要 Content 光标、不需要面板焦点切换:出现时机由 agent 决定,不由导航决定。
        """
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        name, params = self._last_call
        if name != ask.get("tool_name"):        # 对不上就退回只显示 ask 自带的信息
            name, params = ask.get("tool_name", ""), {"detail": ask.get("detail", "")}
        self.approval.open(name, params)
        self._pending_perm = future
        self._set_state("ask")
        goal = self.query_one("#goal", Input)
        goal.disabled = True
        try:
            return await future
        finally:
            self._pending_perm = None
            self.approval.close()
            goal.disabled = False
            goal.focus()
            self._set_state("running" if self._run_start is not None else "idle")

    # ---- 输入 ----

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()

        if self.p_sessions.picking and not text:
            self._confirm_session()          # 选会话时空回车 = 确认
            return
        if not text:
            return
        event.input.value = ""

        if not self._connected:
            await self._view.mount(
                EventRow(SYM["error"], Text("core 已断开。重连: aemeath core", style=S_ERROR))
            )
            self._view.scroll_end(animate=False)
            return

        if text.startswith("/"):
            await self._handle_command(text)
            return

        await self._echo_user(text)
        if self._session_id is None:
            await self._view.mount(EventRow("", Text("session 尚未就绪", style="dim")))
            return

        self._end_answer()
        self.p_thinking.clear()
        self.p_tasks.clear()      # 任务板是"这一轮在干什么",不该留着上一轮的
        self._set_state("running")
        self._run_start = time.monotonic()
        ack = await self._client.send_command(
            "run", {"goal": text, "session_id": self._session_id}
        )
        self._top_run_id = ack.get("run_id")
        self._view.scroll_end(animate=False)

    async def _echo_user(self, text: str) -> None:
        # 空态是垂直居中的,一有内容就该退场,否则中间那块留白会一直顶着
        if self._splash is not None:
            self._splash.remove()
            self._splash = None
        await self._view.mount(Static(LedgerRow("", ""), classes="gap"))
        await self._view.mount(Static(
            LedgerFrame(Text(text), gutter="›", gutter_style=S_MOTION), classes="user"
        ))
        self._view.scroll_end(animate=False)

    # ---- 斜杠命令 ----

    async def _handle_command(self, text: str) -> None:
        view = self._view
        if text == "/resume":
            await self._load_sessions()
            self._enter_picking()
        elif text == "/usage":
            resp = await self._client.send_command(
                "session.usage", {"session_id": self._session_id}
            )
            body = (resp if isinstance(resp, str)
                    else f"in {resp['input_tokens']} · out {resp['output_tokens']} "
                         f"· cache {resp['cache_read']}")
            await view.mount(EventRow("", Text(body, style="dim")))
        elif text == "/mcp":
            resp = await self._client.send_command("mcp.list", {})
            await self._show_mcp(resp["servers"])
        elif text == "/about":
            await self._show_about()
        elif text == "/help":
            await view.mount(EventRow("", Text("  ".join(COMMANDS), style="dim")))
        elif text == "/clear":
            created = await self._client.send_command("session.create", {"mode": "multi_turn"})
            self._session_id = created["session_id"]
            await view.remove_children()
            self._reset_run_state()
            self._ctx_used = 0
            self.p_tasks.clear()
            self.p_thinking.clear()
            self._refresh_status()
            self._mount_splash()          # 清空之后 logo 回来 —— 房间不该是空的
            await self._load_sessions()
        else:
            await view.mount(EventRow("", Text(f"未知命令 {text}", style="dim")))
            await view.mount(EventRow("", Text("  ".join(COMMANDS), style="dim")))
        view.scroll_end(animate=False)

    async def _show_about(self) -> None:
        """`/about` —— 全项目唯一出现她的地方(identity 决策 4:只在显式召唤下现形)。

        窄屏降级是决策的一部分,不是可选优化:宽 < 64 或高 < 34 就只出文字。
        """
        view = self._view
        size = self.query_one("#content", Vertical).content_size
        if size.width >= 64 and size.height >= 20:
            await self._mount(view, Static(splash.Wordmark(), classes="about"))
        rows = [
            (f"AemeathCode  {splash.VERSION}", ""),
            ("一个轻量、可观察、可修改的 Coding Agent Runtime", "dim"),
            ("", ""),
            (f"model      {self._model}", "dim"),
            (f"session    {(self._session_id or '')[:8]}", "dim"),
            (f"context    {self._ctx_used} / {self._window}", "dim"),
        ]
        for content, style in rows:
            await self._mount(view, EventRow("", Text(content, style=style)))

    def _reset_run_state(self) -> None:
        self._spawns.clear()
        self._sub_runs.clear()
        self._calls.clear()
        self._group = None
        self._answer = None
        self._streaming = False
        self._run_start = None
        self._splash = None

    async def _show_mcp(self, servers: list) -> None:
        view = self._view
        if not servers:
            await view.mount(EventRow("", Text("没有已连接的 MCP server", style="dim")))
            return
        for s in servers:
            line = Text()
            line.append((s.get("name") or "").ljust(16))
            if s.get("connected"):
                # 默认只列 server,工具名要展开才看
                line.append(f"{len(s.get('tools', []))} 个工具", style="dim")
                await view.mount(EventRow(SYM["done"], line))
            else:
                line.append(str(s.get("error") or "连接失败"), style=S_ERROR)
                await view.mount(EventRow(SYM["error"], line, gutter_style=S_ERROR))

    # ---- 会话选择(^p / ^n / Enter / Esc)----

    def _enter_picking(self) -> None:
        self.p_sessions.picking = True
        self.p_sessions.add_class("-active")
        # 提示写进面板标题,不往 content 里塞 —— 那属于导航状态,不属于对话内容
        self.p_sessions.border_title = "Sessions  ^↑/^↓ · Enter 恢复 · Esc 取消"
        self.p_sessions.refresh_view()

    def _exit_picking(self) -> None:
        self.p_sessions.picking = False
        self.p_sessions.remove_class("-active")
        self.p_sessions.border_title = "Sessions"
        self.p_sessions.refresh_view()

    def action_session_prev(self) -> None:
        self._enter_picking()
        self.p_sessions.move(-1)

    def action_session_next(self) -> None:
        self._enter_picking()
        self.p_sessions.move(1)

    def action_scroll_up(self) -> None:
        self._view.scroll_page_up(animate=False)

    def action_scroll_down(self) -> None:
        self._view.scroll_page_down(animate=False)

    def _scroller(self):
        """审批打开时 ^j/^k 滚审批预览 —— 那一刻它才是要读的东西。"""
        if self.approval.has_class("-open"):
            return self.query_one("#approval-preview")
        return self.p_thinking

    def action_think_up(self) -> None:
        self._scroller().scroll_page_up(animate=False)

    def action_think_down(self) -> None:
        self._scroller().scroll_page_down(animate=False)

    async def on_key(self, event) -> None:
        # 审批的按键在 App 层收 —— 容器 widget 默认 can_focus=False,靠它自己 focus() 是空操作,
        # 输入框又被禁用了,于是 1/2/3 谁都收不到 → Future 永远不 resolve → 整个界面卡死。
        if self._pending_perm is not None:
            choice = {"1": "allow_once", "2": "allow_always",
                      "3": "deny", "escape": "deny"}.get(event.key)
            if choice and not self._pending_perm.done():
                self._pending_perm.set_result(choice)
                event.stop()
            return
        if event.key == "escape" and self.p_sessions.picking:
            self._exit_picking()
            event.stop()

    @work
    async def _confirm_session(self) -> None:
        row = self.p_sessions.current
        self._exit_picking()
        if row is not None:
            await self._do_resume(row.id)

    async def _do_resume(self, target: str) -> None:
        resp = await self._client.send_command("session.resume", {"session_id": target})
        if isinstance(resp, str):
            await self._view.mount(EventRow("", Text(resp, style="dim")))
            return
        self._session_id = resp["session_id"]
        await self._view.remove_children()
        self._reset_run_state()
        self.p_tasks.clear()
        self.p_skills.clear()
        self.p_thinking.clear()
        self._ctx_used = sum(_estimate_msg_tokens(m) for m in resp["history"])
        self._refresh_status()
        title = resp.get("title") or ""
        await self._view.mount(EventRow("", Text(f"已恢复 · {title}".rstrip(" ·"), style="dim")))
        await self._replay_history(resp["history"])

    async def _replay_history(self, history: list) -> None:
        for msg in history:
            content = _extract_text(msg.get("content"))
            if not content.strip():
                continue
            if msg.get("role") == "user":
                await self._echo_user(content)
            else:
                block = AnswerBlock()
                await self._view.mount(block)
                block.append_token(content)
                block.finalize()


def _estimate_msg_tokens(msg: dict) -> int:
    """resume 时本地粗估一条消息的 token(chars/4),和 compactor 同款启发式。"""
    content = msg.get("content")
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return len(text) // 4


def _extract_text(content) -> str:
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
