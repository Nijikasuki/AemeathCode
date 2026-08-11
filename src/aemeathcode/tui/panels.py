"""侧栏面板 —— lazygit 式的"有名字的房间"。

设计依据见 docs/design/tui-redesign.md。核心是从 lazygit 学来的三条:

1. **边框是承重结构,不是装饰。**它同时干四件事:划分区域、放标题(border_title)、
   放计数(border_subtitle)、表达焦点(边框颜色)。一个元素干四件事 = 高信息密度、零额外噪声。
   (单栏流里"避免边框"是对的;多区域布局里边框是必需的语义元素 —— 这两件事不矛盾。)
2. **每一行同构。**统一是「状态标记 + 主体」,标记宽度对齐成一列,眼睛扫列不读行。
3. **每个房间永远有内容。**空的时候给一句 dim 的占位,不留黑洞。

thinking 单独占一个面板是这套布局最关键的一手:它一直可见(想看随时看),
但**永远不可能淹没正文** —— 比折叠成一行更彻底。
"""
from __future__ import annotations

from dataclasses import dataclass

from rich.console import Group
from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from aemeathcode.tui.ledger import fit
from aemeathcode.tui.theme import S_ADD, S_DIM, S_ERROR, S_LABEL, S_MOTION, S_STRUCT

# 任务状态 → 符号。和 task_update 工具的 enum 对齐。
TASK_SYM = {
    "pending": "○",
    "progressing": "◐",
    "completed": "✧",
    "failed": "×",
}


class Panel(VerticalScroll):
    """一个有名字的房间。标题嵌边框左上,计数嵌边框右下 —— 照抄 lazygit。

    **必须是真正的滚动容器。**之前它是 `Static` + CSS `overflow-y: auto` —— 但 Textual 里
    只有 ScrollView / VerticalScroll 这类容器才真的能滚,给 Static 加 overflow 只是加了条
    滚动条的样子:`scroll_page_up/down` 和 `scroll_to` 全是空操作。
    症状就是 thinking 用 ^j/^k 滚不动、sessions 选到第 8 条时高亮跟不过去。
    """

    def __init__(self, title: str, *, id: str | None = None) -> None:
        super().__init__(id=id, classes="panel")
        self.border_title = title
        self.body = Static("")

    def compose(self):
        yield self.body

    def set_count(self, shown: int, total: int) -> None:
        """`3 of 12` 塞进边框底边,不占内容行。"""
        self.border_subtitle = f"{shown} of {total}" if total else ""

    def empty(self, hint: str) -> None:
        """空态:给一句 dim 的占位,不留黑洞。"""
        self.border_subtitle = ""
        self.body.update(Text(hint, style=S_DIM))


class StatusPanel(Panel):
    """cwd / model / 运行状态。永远有内容。"""

    def __init__(self) -> None:
        super().__init__("Status", id="p-status")

    def render_status(self, *, cwd: str, model: str, state: str) -> None:
        body = Text()
        body.append(fit(cwd, 30) + "\n", style=S_LABEL)
        body.append(fit(model, 30) + "\n", style=S_DIM)
        body.append(state, style=S_MOTION if state.startswith("running") else S_DIM)
        self.body.update(body)


@dataclass
class Task:
    id: str
    content: str
    status: str = "pending"


class TasksPanel(Panel):
    """任务板。

    daemon 没有 task.* 的 RPC,所以这里从 `task_create` / `task_update` 两个工具调用的
    **参数**里就地推导 —— 事件流里已经有全部信息,不需要再加一条协议。
    """

    def __init__(self) -> None:
        super().__init__("Tasks", id="p-tasks")
        self.tasks: list[Task] = []

    def on_tool(self, tool_name: str, params: dict, output: str = "") -> bool:
        """返回 True 表示这次调用改动了任务板。"""
        if tool_name == "task_create":
            content = str(params.get("content", "")).strip()
            if content:
                # id 由 daemon 生成并写在返回文本里,这里先用序号占位,update 时按内容兜底匹配
                self.tasks.append(Task(id=str(len(self.tasks) + 1), content=content))
                return True
        elif tool_name == "task_update":
            tid, status = str(params.get("id", "")), str(params.get("status", ""))
            for task in self.tasks:
                if task.id == tid:
                    task.status = status
                    return True
        return False

    def refresh_view(self) -> None:
        if not self.tasks:
            self.empty("(还没有任务)")
            return
        rows = []
        for task in self.tasks:
            line = Text()
            sym = TASK_SYM.get(task.status, "○")
            running = task.status == "progressing"
            line.append(f" {sym} ", style=S_MOTION if running else S_STRUCT)
            line.append(task.content, style="" if running else S_DIM)
            rows.append(line)
        done = sum(1 for t in self.tasks if t.status == "completed")
        self.set_count(done, len(self.tasks))
        self.body.update(Group(*rows))

    def clear(self) -> None:
        """每问一个新问题就清空 —— 任务板是"这一轮在干什么",不是历史账本。"""
        self.tasks.clear()
        self.refresh_view()


class ThinkingPanel(Panel):
    """thinking 的专属房间。

    实测 thinking 会占满 80% 屏幕,而且和紧随其后的回答**逐字重复**。
    给它一个固定大小的房间之后,这个问题从根上没了:它一直可见,但物理上淹不了正文。
    只显示最新一段,滚动跟随。
    """

    def __init__(self) -> None:
        super().__init__("Thinking", id="p-thinking")
        self._text = ""

    def append(self, token: str) -> None:
        self._text += token
        self._repaint()

    def mark_segment(self) -> None:
        """工具调用之间插一条分隔,**不清空**。

        之前这里是清空 —— 但 agent 的节奏是「想 → 调工具 → 想 → 调工具」,
        每次调工具都清一次,用户看到的永远是刚被清掉的那一刻,面板长期显示"(没有 thinking)"。
        """
        if self._text.strip():
            self._text += "\n\n"

    def _repaint(self) -> None:
        paras = [p.strip() for p in self._text.split("\n\n") if p.strip()]
        if not paras:
            self.empty("(没有 thinking)")
            return
        self.set_count(len(paras), len(paras))
        self.body.update(Text("\n\n".join(paras), style=S_DIM))
        self.scroll_end(animate=False)

    def clear(self) -> None:
        self._text = ""
        self._repaint()


@dataclass
class SessionRow:
    id: str
    title: str
    updated: str


class SessionsPanel(Panel):
    """历史会话。`/resume` 之后在这里选。"""

    def __init__(self) -> None:
        super().__init__("Sessions", id="p-sessions")
        self.rows: list[SessionRow] = []
        self.index = 0
        self.picking = False        # /resume 之后进入选择态

    def load(self, sessions: list[dict]) -> None:
        self.rows = [
            SessionRow(
                id=s.get("id") or "",
                title=(s.get("title") or "(无标题)"),
                updated=(s.get("updated_at") or "")[11:16],
            )
            for s in sessions
        ]
        self.index = 0
        self.refresh_view()

    def move(self, delta: int) -> None:
        if not self.rows:
            return
        self.index = (self.index + delta) % len(self.rows)
        self.refresh_view()
        # 面板本身是可滚动的 Static,选中项移出可视区时要把它滚回来 ——
        # 否则序号在变、标题却停在开头几条,看不见自己选到哪了
        # 让选中项停在可视区中间,而不是等它跑出去才补救
        half = max(self.content_size.height // 2, 1)
        self.scroll_to(y=max(self.index - half, 0), animate=False)

    @property
    def current(self) -> SessionRow | None:
        return self.rows[self.index] if self.rows else None

    def refresh_view(self) -> None:
        if not self.rows:
            self.empty("(还没有历史会话)")
            return
        width = max(self.content_size.width, 24)
        rows = []
        for i, row in enumerate(self.rows):
            sel = self.picking and i == self.index
            line = Text()
            # 选中态用 `▸` + bold + 粉,**不填充整行背景**
            # (lazygit 用蓝色反色条,但 identity.md 禁"大面积填充色块",这是有意的偏离)
            line.append(" ▸ " if sel else "   ", style=S_MOTION)
            line.append(fit(row.title, width - 10), style="bold" if sel else S_DIM)
            rows.append(line)
        self.set_count(self.index + 1 if self.picking else len(self.rows), len(self.rows))
        self.body.update(Group(*rows))


class McpPanel(Panel):
    """MCP server 一览。默认只列 server 名和工具数,工具名要 `/mcp` 才展开。"""

    def __init__(self) -> None:
        super().__init__("MCP", id="p-mcp")
        self.servers: list[dict] = []

    def load(self, servers: list[dict]) -> None:
        self.servers = servers
        self.refresh_view()

    def refresh_view(self) -> None:
        if not self.servers:
            self.empty("(没有 MCP server)")
            return
        rows = []
        for s in self.servers:
            ok = bool(s.get("connected"))
            line = Text()
            line.append(" ✧ " if ok else " × ", style=S_STRUCT if ok else S_ERROR)
            line.append(fit(str(s.get("name") or ""), 16).ljust(16), style=S_LABEL)
            line.append(f"{len(s.get('tools', []))}" if ok else "断开", style=S_DIM)
            rows.append(line)
        online = sum(1 for s in self.servers if s.get("connected"))
        self.set_count(online, len(self.servers))
        self.body.update(Group(*rows))


class SkillsPanel(Panel):
    """本次会话用过的 skill。

    daemon 没有 skill 列表的 RPC,所以这里记录 `use_skill` 实际被调用过的名字 ——
    比列全部可用 skill 更有信息量:它告诉你**这次**用上了什么。
    """

    def __init__(self) -> None:
        super().__init__("Skills", id="p-skills")
        self.names: list[str] = []

    def used(self, name: str) -> None:
        if name and name not in self.names:
            self.names.append(name)
            self.refresh_view()

    def clear(self) -> None:
        self.names.clear()
        self.refresh_view()

    def refresh_view(self) -> None:
        if not self.names:
            self.empty("(本次没用 skill)")
            return
        rows = []
        for name in self.names:
            line = Text()
            line.append(" ✧ ", style=S_STRUCT)
            line.append(name, style=S_LABEL)
            rows.append(line)
        self.set_count(len(self.names), len(self.names))
        self.body.update(Group(*rows))


def approval_preview(tool_name: str, params: dict, *, limit: int = 200) -> tuple[Text, str]:
    """审批时该给用户看的东西 —— 返回 (预览, 边框右下角的计量)。

    为什么这件事重要:之前审批只显示 `write_file  bubble_sort.py` 一行,
    **用户是在对一个看不见内容的写入操作点"允许"**。那不叫审批,叫盲签。

    完整参数由 **ask 信封自带**(`AskEnvelope.params`)。最早的写法是去事件流里捞上一条
    `tool.call_started` 的 params —— 那依赖"start 先于审批到达"这个巧合;后来把 start
    挪到了权限检查之后(P1-5),巧合就没了。审批是一次独立的请求,该自己说清求的是什么。
    """
    text = Text()
    if tool_name == "write_file":
        lines = str(params.get("content", "")).splitlines()
        for line in lines[:limit]:
            text.append("  + ", style=S_ADD)       # diff 约定:+ 标绿,内容用正常前景色
            text.append(line + "\n")
        if len(lines) > limit:
            text.append(f"  ⋮ 还有 {len(lines) - limit} 行\n", style=S_DIM)
        return text, f"{len(lines)} 行"
    if tool_name == "bash":
        # 完整命令,不截断 —— 长命令里藏着的东西正是审批要看的
        text.append("  $ ", style=S_ADD)
        text.append(str(params.get("command", "")))
        return text, ""
    for key, value in params.items():
        text.append(f"  {key}  ", style=S_LABEL)
        text.append(f"{value}\n")
    return text, ""


class ApprovalPane(Vertical):
    """审批面板 —— **只在需要做决定时出现**,固定在 Content 底部。

    这是整套 Detail 设计的核心取舍:把详情绑定到"必须做决定"的那一刻,而不是
    绑定到"随便浏览"。于是完全不需要 Content 光标、面板焦点切换、抢按键 ——
    出现时机由 agent 决定,不由用户导航决定。
    """

    DEFAULT_CSS = """
    ApprovalPane { display: none; height: auto; max-height: 60%; border: round $warning;
                   border-title-color: $warning; border-subtitle-color: $warning; padding: 0 1; }
    ApprovalPane.-open { display: block; }
    /* 预览可滚动,选项固定在底部 —— 按钮是全屏最不能被截掉的东西。
       上一版把两者放在同一个 Static 里,长文件直接把选项顶出了 max-height。 */
    ApprovalPane > #approval-preview { height: 1fr; scrollbar-size-vertical: 1; }
    ApprovalPane > #approval-choices { dock: bottom; height: 1; }
    """

    def __init__(self) -> None:
        super().__init__(id="approval")
        self.body = Static("")
        self._choices = Static("", id="approval-choices")

    def compose(self):
        yield VerticalScroll(self.body, id="approval-preview")
        yield self._choices

    def open(self, tool_name: str, params: dict) -> None:
        preview, metric = approval_preview(tool_name, params)
        target = target_hint(tool_name, params)
        self.border_title = f"需要授权 · {tool_name}{'  ' + target if target else ''}"
        self.border_subtitle = f"{metric}  ^j/^k 滚动" if metric else "^j/^k 滚动"
        choices = Text()
        for i, label in enumerate(("允许一次", "总是允许", "拒绝")):
            choices.append(f"  {i + 1} ", style=S_MOTION)
            choices.append(f"{label}     ", style="bold")
        self.body.update(preview)
        self._choices.update(choices)
        self.add_class("-open")

    def close(self) -> None:
        self.remove_class("-open")


def target_hint(tool_name: str, params: dict) -> str:
    for key in ("path", "command", "goal", "name"):
        if key in params:
            return fit(str(params[key]), 48)
    return ""


class ChangesPanel(Panel):
    """本轮碰过的文件。

    数据来自 `write_file` 的调用参数 —— 和任务板一样,事件流里信息已经够了,
    不需要给 daemon 加协议。`+N` 是写入的行数(不是 diff 的增量:
    TUI 手上没有旧内容,拿不到真正的增删行数,所以只报"写了多少行",不谎报成 diff)。
    """

    def __init__(self) -> None:
        super().__init__("Changes", id="p-changes")
        self.files: dict[str, int] = {}

    def on_write(self, path: str, content: str) -> None:
        if path:
            self.files[path] = len(content.splitlines())
            self.refresh_view()

    def clear(self) -> None:
        self.files.clear()
        self.refresh_view()

    def refresh_view(self) -> None:
        if not self.files:
            self.empty("(本轮没改文件)")
            return
        width = max(self.content_size.width, 20)
        rows = []
        for path, lines in self.files.items():
            line = Text()
            line.append(" M ", style=S_ADD)
            # 路径太长时砍前面留后面 —— 文件名比目录有信息量
            shown = path if len(path) <= width - 9 else "…" + path[-(width - 10):]
            line.append(shown.ljust(max(width - 9, 4)), style=S_LABEL)
            line.append(f"+{lines}", style=S_DIM)
            rows.append(line)
        self.set_count(len(self.files), len(self.files))
        self.body.update(Group(*rows))
