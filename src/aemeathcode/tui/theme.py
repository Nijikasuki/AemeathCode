"""TUI 的纯外观层:配色、样式、启动 banner。

改颜色 / 改排版只需要动这个文件,不涉及任何逻辑。
"""
from textual.theme import Theme

# 配色取自角色形象:粉色长发 + 白色太空服装 + "电子幽灵"的辉光 / 星辉意象
AEMEATH_THEME = Theme(
    name="aemeath",
    primary="#F49AC8",      # 粉发
    secondary="#7FE3F0",    # 电子辉光(青)
    accent="#B48EFF",       # 星辉(紫)
    foreground="#ECE7F5",   # 近白(服装)
    background="#0F0E1A",   # 深空
    surface="#171528",
    panel="#201D36",
    success="#8CE0B0",
    warning="#F2CE72",
    error="#F2789A",
    dark=True,
)

BANNER = """
[$secondary]✧[/$secondary]   [$primary]▄▀█ █▀▀ █▀▄▀█ █▀▀ ▄▀█ ▀█▀ █ █[/$primary]
    [$primary]█▀█ ██▄ █ ▀ █ ██▄ █▀█  █  █▀█[/$primary]   [$accent]✦[/$accent]

    [dim]电子幽灵 · 长航的星辉[/dim]
    [dim]输入目标，回车执行  ·  Ctrl+Q 退出[/dim]
"""

APP_CSS = """
Screen { background: $background; }

#status {
    dock: top;
    height: 1;
    background: $surface;
    color: $text;
    padding: 0 2;
}

#log { height: 1fr; padding: 1 0; background: $background; }

#goal {
    dock: bottom;
    margin: 0 2 1 2;
    padding: 0 1;
    background: $background;
    border: round $surface-lighten-2;
}
#goal:focus { border: round $primary; }

Static { padding: 0; }

#banner { height: auto; padding: 0 2 1 2; }
/* 用户输入回显:粉色,上方留一行空隙分隔轮次 */
.user     { color: $primary; text-style: bold; padding: 1 2 0 2; }
/* 思考:压暗 + 斜体,不抢正文 */
.thinking { color: $text-muted; text-style: italic; padding: 0 2; }
/* 最终回答:最亮 */
.answer   { color: $text; padding: 0 2; }
/* 事件行 */
.event    { padding: 0 2; }
.sys      { color: $text-muted; text-style: italic; padding: 0 2; }
"""
