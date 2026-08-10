"""台账排版的几何层 —— 整个界面的地基。

一行台账长这样(≥100 列时):

     ┌ 1 空格
     │ ┌──────── gutter,右对齐
     │ │        ┌ 1 空格
     │ │        │┌ 竖线
     │ │        ││┌ 1 空格
       step 3   │ 先扫一遍目录
            ◇   │ read_file   tests/conftest.py                    41 行
     └── chrome ┘└──────────── content ────────────────────────────────┘

三条规则:

1. **宽度按显示格算,不按 len() 算。**`◇ ⋄ ×` 这些是 East Asian Ambiguous 宽度,
   `⚡` 是 Wide,CJK 是 Wide —— `len("中")==1` 但它占 2 格。用 rich 的 cell_len。
2. **内容区吃满可用宽度。**限宽由外层面板的边框负责,这里再卡一次会让面板右半边空着。
3. **窄屏分四档降级**,最窄那档退化成"符号 + 缩进",层级依然成立。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, RenderResult
from rich.segment import Segment
from rich.text import Text

from aemeathcode.tui.theme import S_STRUCT

# ---- 符号表 ----------------------------------------------------------------
# 不许随意扩充。新增符号要先证明现有词汇表表达不了。

SYM = {
    "idle": "·",        # 空闲 / 呼吸点
    "busy": "◌",        # 进行中(thinking / tool 执行中 / 生成中)
    "read": "◇",        # 只读工具
    "write": "◆",       # 改变世界的工具
    "subagent": "✦",
    "compact": "⋄",
    "done": "✧",
    "error": "×",
    "ask": "?",         # 等待授权
    "fold": "⋮",        # 折叠省略
    "expand": "⌄",
    "collapse": "⌃",
}

# 单色 / 窄字体降级集(AEMEATH_ASCII=1)。
# 上面那套里 `◇ ◌ ⋄ × ·` 都是 East Asian **Ambiguous** 宽度 —— 在某些终端 / 字体下
# 会渲染成全角,把整个 gutter 的列对齐打歪。给一条不赌运气的退路。
SYM_ASCII = {
    "idle": ".", "busy": "o", "read": "-", "write": "+", "subagent": "*",
    "compact": "~", "done": "v", "error": "x", "ask": "?", "fold": ":",
    "expand": "v", "collapse": "^",
}

if os.environ.get("AEMEATH_ASCII"):
    SYM = SYM_ASCII

RULE = "|" if os.environ.get("AEMEATH_ASCII") else "│"
RULE_NESTED = ":" if os.environ.get("AEMEATH_ASCII") else "╎"   # subagent 嵌套,和主线区分

# 内容区上限。**单栏时代**这个值用来防止 250 列的正文一行铺 200 字符;
# 改成多面板布局之后,面板边框本身已经限宽了,再卡一次会让右半边空着。
CONTENT_MAX = 400
METRIC_MIN = 40     # content 窄于这个就不显示右侧 metric(它是最低价值的信息)


@dataclass(frozen=True)
class Geometry:
    """某个终端宽度下的列几何。"""
    gutter_w: int      # gutter 内容宽度
    rule: bool         # 画不画竖线
    chrome: int        # gutter 区总宽(含空格和竖线)
    content_w: int     # 内容区宽度
    labels: bool       # gutter 放不放得下 "step 3" / "2.4s" 这种标签

    @property
    def show_metric(self) -> bool:
        return self.content_w >= METRIC_MIN


def geometry(width: int) -> Geometry:
    """按终端宽度算出这一档的列几何。四档降级见 docs/design/tui-redesign.md §五.14。"""
    if width >= 100:
        chrome, gutter_w, rule, labels = 12, 8, True, True
    elif width >= 70:
        chrome, gutter_w, rule, labels = 8, 4, True, False
    elif width >= 50:
        chrome, gutter_w, rule, labels = 4, 2, False, False
    else:
        chrome, gutter_w, rule, labels = 3, 1, False, False
    content_w = min(max(width - chrome, 8), CONTENT_MAX)
    return Geometry(gutter_w, rule, chrome, content_w, labels)


def fit(text: str, width: int) -> str:
    """按**显示格**截断,超出补 `…`。cell_len 而不是 len —— CJK 一个字占两格。"""
    if width <= 0:
        return ""
    if cell_len(text) <= width:
        return text
    out = ""
    used = 0
    for ch in text:
        w = cell_len(ch)
        if used + w > width - 1:
            break
        out += ch
        used += w
    return out + "…"


def pad_to(text: str, width: int) -> str:
    """按显示格右侧补空格到指定宽度。"""
    return text + " " * max(width - cell_len(text), 0)


class LedgerRow:
    """一行台账 = gutter + 竖线 + 内容(可自动换行) + 右对齐 metric。

    内容换行时,续行的 gutter 留空、竖线继续画 —— 这样一条竖直基线贯穿全屏,
    连发几十次 tool call 视觉上也不会晃。

    gutter 分两种:
      * 符号(`◇` `×` `✦`)—— 窄屏也保留,它承载语义
      * 标签(`step 3` `2.4s`)—— 窄屏第一个被丢掉,它只是锦上添花
    """

    def __init__(
        self,
        gutter: str = "",
        content: str | Text = "",
        metric: str = "",
        *,
        is_symbol: bool = True,
        gutter_style: str = S_STRUCT,
        content_style: str = "",
        metric_style: str = S_STRUCT,
        indent: int = 0,
        rule_char: str = RULE,
        metric_col: int = 0,   # metric 左边界(0=贴内容区右端)。同组各行传同一个值就能对齐
    ) -> None:
        self.gutter = gutter
        self.content = content
        self.metric = metric
        self.is_symbol = is_symbol
        self.gutter_style = gutter_style
        self.content_style = content_style
        self.metric_style = metric_style
        self.indent = indent            # 内容额外缩进(subagent 嵌套 / 错误详情)
        self.rule_char = rule_char
        self.metric_col = metric_col

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        geo = geometry(options.max_width)
        dim = console.get_style(self.gutter_style, default="dim")
        rule_style = console.get_style(S_STRUCT, default="dim")
        body_style = console.get_style(self.content_style, default="")
        metric_style = console.get_style(self.metric_style, default="dim")

        # gutter:标签在窄档被丢掉,符号永远保留
        gutter = fit(self.gutter if (self.is_symbol or geo.labels) else "", geo.gutter_w)
        # 右对齐:按**显示格**补左空格(str.rjust 会把 CJK 算成 1 格,不能用)
        gutter_cell = " " + " " * max(geo.gutter_w - cell_len(gutter), 0) + gutter

        body_w = geo.content_w - self.indent
        metric = self.metric if geo.show_metric else ""
        # metric 占右侧,内容让出位置(留 2 格间隔)。
        # metric_col 给定时按它对齐 —— 否则短内容会把 metric 甩到很远,中间一大片空,
        # 读起来像一张缺了一列的表格。
        if metric and self.metric_col:
            text_w = min(self.metric_col, body_w - cell_len(metric) - 2)
        else:
            text_w = body_w - (cell_len(metric) + 2 if metric else 0)
        text_w = max(text_w, 8)

        text = self.content if isinstance(self.content, Text) else Text(self.content)
        lines = text.wrap(console, text_w) if text.plain else [Text("")]

        for i, line in enumerate(lines):
            # gutter 只画第一行,续行留空
            if i == 0:
                yield Segment(gutter_cell, dim)
            else:
                yield Segment(" " * (1 + geo.gutter_w), dim)
            if geo.rule:
                yield Segment(" " + self.rule_char + " ", rule_style)
            else:
                yield Segment(" ")
            if self.indent:
                yield Segment(" " * self.indent)

            plain = line.plain
            yield Segment(pad_to(plain, text_w), body_style)
            if metric and i == 0:
                yield Segment("  " + metric, metric_style)
            yield Segment("\n")


class LedgerFrame:
    """把**任意** rich renderable 塞进内容列,并给它的每一行都补上 gutter + 竖线。

    这是"竖线常驻"的关键:最终回答、Markdown、代码块……全都从这里过一遍,
    所以那条竖直基线从屏幕顶贯到底,一次都不断。

    之前的版本让最终回答顶格跨出竖线做层级 —— 结果那条线一会儿有一会儿没有,
    整个版面是断的。层级改由**亮度 + 上下留白**承担,不再靠 outdent。
    """

    def __init__(self, renderable, *, gutter: str = "", indent: int = 0,
                 rule_char: str = RULE, gutter_style: str = S_STRUCT) -> None:
        self.renderable = renderable
        self.gutter = gutter
        self.indent = indent
        self.rule_char = rule_char
        self.gutter_style = gutter_style

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        geo = geometry(options.max_width)
        gutter_style = console.get_style(self.gutter_style, default="dim")
        rule_style = console.get_style(S_STRUCT, default="dim")
        inner = options.update_width(max(geo.content_w - self.indent, 8))
        gutter = fit(self.gutter, geo.gutter_w)
        head = " " + " " * max(geo.gutter_w - cell_len(gutter), 0) + gutter
        blank = " " * (1 + geo.gutter_w)

        for i, line in enumerate(console.render_lines(self.renderable, inner, pad=False)):
            yield Segment(head if i == 0 else blank, gutter_style)
            if geo.rule:
                yield Segment(" " + self.rule_char + " ", rule_style)
            else:
                yield Segment(" ")
            if self.indent:
                yield Segment(" " * self.indent)
            yield from line
            yield Segment("\n")


