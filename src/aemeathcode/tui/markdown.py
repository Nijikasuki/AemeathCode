"""安静版 Markdown —— 覆盖 rich 的默认主题。

为什么需要这个文件:`rich.markdown.Markdown` 的默认样式是给**打印文档**设计的 ——
标题带下划线和品红、`hr` 渲染成横跨整个终端宽度的虚线、代码块带实心灰底。
这套东西塞进对话流,回答就长得像一份 GitHub README,而不像有人在跟你说话。
(诊断见 docs/design/tui-redesign.md §一.3)

这里做两件事:
  * **样式**:用 rich Theme 覆盖所有 `markdown.*` 样式名 —— 去色、去下划线、去填充底
  * **结构**:h1 不居中、hr 不铺满、代码块不带背景 —— 这几条改样式改不掉,得换元素类
"""
from __future__ import annotations

from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import CodeBlock, Heading, HorizontalRule, Markdown
from rich.segment import Segment
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme

# 去装饰:标题只留 bold,代码去底色,引用和列表退回 dim。
# 一条都不给颜色 —— 回答里的颜色应该由内容本身决定,不由 Markdown 语法决定。
QUIET_MD = Theme(
    {
        "markdown.h1": "bold",
        "markdown.h2": "bold",
        "markdown.h3": "bold",
        "markdown.h4": "bold",
        "markdown.h5": "bold",
        "markdown.h6": "bold",
        "markdown.h7": "bold",
        "markdown.h1.border": "none",
        "markdown.code": "bold",           # 行内 code:只 bold,不反色
        "markdown.code_block": "",         # 背景在 QuietCodeBlock 里关掉
        "markdown.block_quote": "dim",
        "markdown.list": "",
        "markdown.item.bullet": "dim",
        "markdown.item.number": "dim",
        "markdown.hr": "dim",
        "markdown.link": "underline",
        "markdown.link_url": "dim underline",
        "markdown.table.border": "dim",
        "markdown.table.header": "bold",
    },
    inherit=True,
)


class QuietHeading(Heading):
    """标题一律左对齐。rich 默认把 h1 居中 —— 那是文档排版,不是对话。"""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        text = self.text.copy()
        text.justify = "left"
        yield text


class QuietRule(HorizontalRule):
    """`hr` 只画 3 个字符,不铺满整行。

    250 列的终端上,rich 默认那条横跨全宽的虚线是屏幕上最抢眼的东西 ——
    而它表达的只是"换个话题"。
    """

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield Text("───", style=console.get_style("markdown.hr", default="dim"))


class QuietCodeBlock(CodeBlock):
    """代码块:去掉实心底,左侧加一条 dim 竖线。

    保留语法高亮(它是功能,不是装饰),但背景必须透明 —— 那块灰底是"模板感"最直接的来源。
    """

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        code = str(self.text).rstrip()
        syntax = Syntax(
            code,
            self.lexer_name,
            theme=self.theme,
            word_wrap=True,
            padding=0,
            background_color="default",   # ← 关键:不画背景色块
        )
        bar = Style(dim=True)
        inner = options.update_width(max(options.max_width - 2, 4))
        for line in console.render_lines(syntax, inner, pad=False):
            yield Segment("│ ", bar)
            yield from line
            yield Segment("\n")


class QuietMarkdown(Markdown):
    """把上面三个元素换进去,并在渲染时压上 QUIET_MD 主题。"""

    elements = {  # noqa: RUF012 —— rich Markdown 的类属性约定
        **Markdown.elements,
        "heading_open": QuietHeading,
        "hr": QuietRule,
        "fence": QuietCodeBlock,
        "code_block": QuietCodeBlock,
    }

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        with console.use_theme(QUIET_MD):
            yield from super().__rich_console__(console, options)
