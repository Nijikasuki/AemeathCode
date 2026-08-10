"""TUI 的组件层 —— 每个 widget 自己持有状态、自己管自己的显示。

排版全部走 ledger.py 的几何,所以这里只关心"这一类信息长什么样"。

  * AnswerBlock   —— 最终回答。**唯一顶格的东西**,跨过整个 gutter 区
  * ToolGroup     —— 连续的只读工具合并成一组,跑完收起
  * ToolRow       —— 改变世界的工具(write/bash/...),永远单独一行
  * SubagentBlock —— 子 agent,嵌套一级缩进 + 换竖线字符
  * EventRow      —— 其余一次成型的事件行
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from rich.cells import cell_len
from rich.console import Group, RenderableType
from rich.text import Text
from textual.widget import Widget
from textual.widgets import Static

from aemeathcode.tui.ledger import RULE, SYM, LedgerFrame, LedgerRow
from aemeathcode.tui.markdown import QuietMarkdown
from aemeathcode.tui.theme import S_ERROR, S_LABEL, S_MOTION, S_STRUCT

# 只读工具可以合并成组;改变世界的工具永远单独一行 —— 用户必须看见每一次写入和每一条命令。
READONLY = {"read_file", "list_dir", "task_get", "task_list"}
MUTATING = {"write_file", "bash", "note_save", "task_create", "task_update", "spawn_agent"}
# MCP 工具名不可预知,用前缀启发式判只读;判不出来的当成"要单独显示",宁可啰嗦不可隐瞒
READONLY_PREFIXES = ("get_", "list_", "search_", "read_", "find_", "fetch_")

GROUP_FOLD = 5      # 同一组超过这个条数就折叠(= 重载模式阈值,一个数字服务两处)
GROUP_HEAD = 3      # 折叠后保留的头部条数
PREVIEW = 64        # thinking / 参数摘要的截断长度


def is_readonly(tool_name: str) -> bool:
    if tool_name in MUTATING:
        return False
    return tool_name in READONLY or tool_name.startswith(READONLY_PREFIXES)


def target_of(tool_name: str, params: dict[str, Any]) -> str:
    """一次工具调用最该被看见的那个参数。

    旧版把整个 params JSON 回显出来(`{"path": "tests/conftest.py"}`)——
    字段名是给机器看的,人只需要知道"对哪个东西动手"。
    """
    for key in ("path", "command", "goal", "file_path", "query", "pattern", "name", "content"):
        if key in params:
            return str(params[key])
    if "id" in params and "status" in params:          # task_update
        return f"#{params['id']} → {params['status']}"
    if not params:
        return ""
    return json.dumps(params, ensure_ascii=False)


def metric_of(tool_name: str, content: str, *, is_error: bool) -> str:
    """从工具输出里提炼**一个**量化事实。

    不是预览输出 —— 预览是旧版最占地方的东西之一,而且几乎没人读。
    """
    if is_error or not content:
        return ""
    if tool_name == "list_dir":
        n = len([ln for ln in content.splitlines() if ln.strip()])
        return f"{n} 项" if content != "目录为空" else "空"
    if tool_name == "write_file":
        return content.split("→")[0].replace("已写入", "").strip()
    if tool_name == "bash":
        body = content.removeprefix("stdout:")
        n = len(body.splitlines())
        return f"{n} 行" if n > 1 else ""
    n = len(content.splitlines())
    return f"{n} 行" if n > 1 else ""


def humanize(tool_name: str, content: str) -> str:
    """把工具的原始输出整理成人看的。

    bash 失败时 content 是 `stdout:X,stderr:Y,returncode:N` 拼出来的一整串,
    直接摊在界面上没法读。用 rsplit 从右边拆(输出里出现这几个标记的概率远低于左边),
    拆不开就原样返回 —— 宁可难看,不可丢信息。
    """
    if tool_name != "bash":
        return content
    body, sep, code = content.rpartition(",returncode:")
    if not sep:
        return content.removeprefix("stdout:")
    out, _, err = body.rpartition(",stderr:")
    out = out.removeprefix("stdout:")
    parts = [p.strip() for p in (err, out) if p.strip()]
    if code.strip() not in ("", "0"):
        parts.append(f"退出码 {code.strip()}")
    return "\n".join(parts) or content


@dataclass
class ToolCall:
    """一次工具调用的全部状态。渲染成什么样由外面的 widget 决定。"""
    name: str
    params: dict[str, Any]
    started_at: str = ""
    output: str = ""
    elapsed_ms: int = 0
    is_error: bool = False
    finished: bool = False

    @property
    def target(self) -> str:
        return target_of(self.name, self.params)

    @property
    def metric(self) -> str:
        if not self.finished:
            return ""
        return metric_of(self.name, self.output, is_error=self.is_error)

    @property
    def symbol(self) -> str:
        if not self.finished:
            return SYM["busy"]
        if self.is_error:
            return SYM["error"]
        return SYM["read"] if is_readonly(self.name) else SYM["write"]

    def line(self) -> Text:
        """`read_file   tests/conftest.py` —— 工具名补齐到 12 格,目标跟在后面。"""
        text = Text()
        text.append(self.name.ljust(12), style=S_LABEL)
        text.append(self.target)
        return text


class AnswerBlock(Static):
    """agent 说的话。**留在竖线右侧的内容列里** —— 竖线是常驻的,不许被跨过。

    层级不靠缩进,靠两件事:
      * **亮度** —— 最终回答是前景色,中间叙述压 dim(后面跟了 tool call 就降级)
      * **留白** —— 最终回答上下各空一行,叙述不空

    两阶段渲染:流的过程中是纯文本(打字机,便宜);定格时重渲染成安静版 Markdown。
    """

    def __init__(self, *, rule_char: str = RULE) -> None:
        super().__init__("", classes="answer")
        self._text = ""
        self._finalized = False
        self._narration = False
        self._rule = rule_char

    def _frame(self, renderable):
        # gutter 给个标识:竖线左边不该一路空着 —— 一眼要能看出"这段是谁说的"
        mark = "" if self._narration else SYM["done"]
        frame = LedgerFrame(renderable, gutter=mark, rule_char=self._rule)
        if self._narration:
            return frame
        # 最终回答上方空一行 —— 但那一行也带竖线,基线不断。
        # 用 CSS padding 做不到这点:padding 是纯空白,会把线切断。
        return Group(LedgerRow("", "", rule_char=self._rule), frame)

    @property
    def answer_text(self) -> str:
        """给复制功能用的纯文本(原始 markdown,不是渲染后的)。"""
        return self._text

    def demote(self) -> None:
        """后面跟了 tool call → 这段是过程叙述不是最终回答。压暗 + 去掉留白。"""
        self._narration = True
        self.add_class("-narration")
        if self._finalized and self._text.strip():
            self.update(self._frame(QuietMarkdown(self._text)))

    def append_token(self, token: str) -> None:
        if self._finalized:
            return
        self._text += token
        # Text() 不解析标记,所以模型原始输出里的 [..] 不会把 Rich 打崩
        text = Text(self._text)
        text.append("▌", style=S_MOTION)   # 流式游标:全屏唯一在动的粉
        self.update(self._frame(text))

    def finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        if self._text.strip():
            self.update(self._frame(QuietMarkdown(self._text)))
        else:
            self.remove()


class ToolGroup(Static):
    """连续的只读工具 = 一个视觉组。

    人的心智里"读了 22 个文件"是**一件事**,不是 22 件事。旧版把每个 event 一比一
    翻译成一个块,连发 22 次就是一面格子墙 —— 那是把数据结构当成了视觉结构。
    """

    DEFAULT_CSS = "ToolGroup { height: auto; }"

    def __init__(self, *, rule_char: str = RULE) -> None:
        super().__init__()
        self.calls: list[ToolCall] = []
        self._group_closed = False
        self._elapsed_ms = 0
        self._expanded = False
        self._rule = rule_char

    def add(self, call: ToolCall) -> None:
        self.calls.append(call)
        self._repaint()

    def close(self, elapsed_ms: int) -> None:
        """组结束:收成一行摘要。往上滚看到的是一串组标题,不是 200 行 tool 日志。

        例外:**组里有失败就不收起**。错误不许被折叠藏起来 —— 这是"可观察"的底线。
        """
        self._group_closed = True
        if self.has_error:
            self._expanded = True
        self._elapsed_ms = elapsed_ms
        self._repaint()

    @property
    def has_error(self) -> bool:
        return any(c.is_error for c in self.calls)

    def on_click(self) -> None:
        if self._group_closed:
            self._expanded = not self._expanded
            self._repaint()

    def _metric_col(self) -> int:
        """本组所有行内容的最大显示宽度 + 2 —— 让 metric 贴着内容排,而不是甩到屏幕右边。"""
        return max((cell_len(c.line().plain) for c in self.calls), default=0) + 2

    def _row(self, call: ToolCall) -> LedgerRow:
        return LedgerRow(
            call.symbol, call.line(), call.metric,
            metric_col=self._metric_col(),
            gutter_style=S_ERROR if call.is_error else "dim",
            content_style="dim",
            rule_char=self._rule,
        )


    def _repaint(self) -> None:
        """内容行数会变,必须整体替换 renderable(而不是 refresh)——
        Static 会据此重算 height: auto。"""
        self.update(self._build())

    def on_mount(self) -> None:
        self._repaint()

    def _build(self) -> RenderableType:
        rows: list[RenderableType] = []

        if self._group_closed and not self._expanded:
            mark = SYM["collapse"] if self._expanded else SYM["expand"]
            n = len(self.calls)
            secs = f"{self._elapsed_ms / 1000:.1f}s"
            sym = SYM["error"] if self.has_error else SYM["read"]
            summary = Text(f"探索 {n} 个文件" if n > 1 else self.calls[0].line().plain, style="dim")
            rows.append(LedgerRow(sym, summary, f"{secs}  {mark}",
                                  metric_col=cell_len(summary.plain) + 2,
                                  gutter_style=S_ERROR if self.has_error else S_STRUCT,
                                  rule_char=self._rule))
            return Group(*rows)

        # 展开 / 进行中:头 3 条 + 折叠计数 + 正在跑的那条。失败永远不进折叠。
        visible = self.calls
        hidden = 0
        if not self._expanded and len(self.calls) > GROUP_FOLD:
            head = self.calls[:GROUP_HEAD]
            tail = [c for c in self.calls[GROUP_HEAD:] if c.is_error or not c.finished]
            hidden = len(self.calls) - len(head) - len(tail)
            visible = head + tail

        for call in visible:
            rows.append(self._row(call))
            if call.is_error and call.output:
                # 失败自动展开错误内容 —— 只换一个词的颜色,在 tool 墙里必然被漏掉
                rows.append(LedgerRow("", Text(humanize(call.name, call.output).strip(), style=S_ERROR),
                                      indent=2, rule_char=self._rule))
            if hidden and call is visible[GROUP_HEAD - 1]:
                rows.append(LedgerRow(SYM["fold"], Text(f"还有 {hidden} 个", style="dim"),
                                      SYM["expand"], rule_char=self._rule))
        return Group(*rows)


class ToolRow(Static):
    """一次改变世界的工具调用(write_file / bash / note_save / task_*)。

    永远单独一行、永远不进折叠组 —— 用户必须看见每一次写入和每一条命令。
    """

    DEFAULT_CSS = "ToolRow { height: auto; }"

    def __init__(self, call: ToolCall, *, rule_char: str = RULE) -> None:
        super().__init__()
        self.call = call
        self._expanded = False
        self._rule = rule_char

    def update_result(self) -> None:
        self._repaint()

    def on_click(self) -> None:
        if self.call.finished:
            self._expanded = not self._expanded
            self._repaint()


    def _repaint(self) -> None:
        """内容行数会变,必须整体替换 renderable(而不是 refresh)——
        Static 会据此重算 height: auto。"""
        self.update(self._build())

    def on_mount(self) -> None:
        self._repaint()

    def _build(self) -> RenderableType:
        call = self.call
        mark = ""
        if call.finished and call.output and not call.is_error:
            mark = SYM["collapse"] if self._expanded else SYM["expand"]
        metric = f"{call.metric}  {mark}".strip() if mark else call.metric
        rows: list[RenderableType] = [
            LedgerRow(call.symbol, call.line(), metric,
                      metric_col=cell_len(call.line().plain) + 2,
                      gutter_style=S_ERROR if call.is_error else S_STRUCT,
                      rule_char=self._rule)
        ]
        if call.is_error and call.output:
            rows.append(LedgerRow("", Text(humanize(call.name, call.output).strip(), style=S_ERROR),
                                  indent=2, rule_char=self._rule))
        elif self._expanded and call.output:
            rows.append(LedgerRow("", Text(humanize(call.name, call.output).rstrip(), style="dim"),
                                  indent=2, rule_char=self._rule))
        return Group(*rows)


class SubagentBlock(Widget):
    """子 agent —— 事件归属到父块名下,不平铺成兄弟。

    嵌套只做**一层**视觉缩进:gutter 里换 `╎` 竖线 + 内容缩进,更深的嵌套复用同一层,
    靠竖线的连续性表达从属关系。跑完自动收起(子 transcript 和父的转述重复)。
    """

    DEFAULT_CSS = """
    SubagentBlock { height: auto; }
    SubagentBlock > .sub-body { height: auto; }
    SubagentBlock.-collapsed > .sub-body { display: none; }
    """

    def __init__(self, goal: str) -> None:
        super().__init__()
        self.goal = goal
        self._header = Static()
        self._body = Widget(classes="sub-body")
        self._steps = 0
        self._elapsed_ms = 0
        self._done = False

    def compose(self):
        yield self._header
        yield self._body

    def on_mount(self) -> None:
        self._render_header()

    @property
    def body(self) -> Widget:
        return self._body

    def _render_header(self) -> None:
        if self._done:
            mark = SYM["expand"] if self.has_class("-collapsed") else SYM["collapse"]
            metric = f"{self._steps} 步 · {self._elapsed_ms / 1000:.1f}s  {mark}"
        else:
            metric = SYM["busy"]
        line = Text()
        line.append("spawn_agent ", style="dim")
        line.append(self.goal)
        self._header.update(LedgerRow(SYM["subagent"], line, metric))

    def finish(self, steps: int, elapsed_ms: int) -> None:
        self._steps, self._elapsed_ms, self._done = steps, elapsed_ms, True
        self.add_class("-collapsed")
        self._render_header()

    def on_click(self) -> None:
        if self._done:
            self.toggle_class("-collapsed")
            self._render_header()


class EventRow(Static):
    """其余一次成型的事件行(压缩 / run 收尾 / 系统提示)。"""

    def __init__(self, gutter: str, content: str | Text, metric: str = "", **kw: Any) -> None:
        super().__init__(LedgerRow(gutter, content, metric, **kw))


