"""TUI 的纯外观层:配色与样式。

改颜色 / 改排版只需要动这个文件,不涉及任何逻辑。

配色的一条硬规则(docs/design/identity.md §3):
**颜色永远不是唯一的区分手段。**任何用颜色表达的状态,必须同时有符号、位置或缩进上的
区分 —— 在 NO_COLOR=1 和单色终端下,界面语义必须完全不丢。

第二条:**粉 = 正在动。**静止的界面上不出现粉。一旦出现粉,那里必须正在发生什么;
流结束了粉就要退回去。所以 accent 只用在:流式游标、呼吸点、running 计时、正在跑的符号。
"""
import os

from textual.theme import Theme

# 低饱和的浅粉,接近角色发色。终端 ANSI 的 magenta 太冲,会比立绘脏一个档次,所以给真彩值。
MOTION = "#EFA8C8"

AEMEATH_THEME = Theme(
    name="aemeath",
    primary=MOTION,          # 只给"正在动的东西"
    secondary="#8FA8C4",     # 极弱的辅助光
    accent=MOTION,
    foreground="#E4E1EC",
    background="#0E0D14",
    surface="#15141D",
    panel="#1C1A26",
    success="#8CBF9E",
    warning="#D9B86A",
    error="#D96A72",         # 红只留给错误,不当装饰
    dark=True,
)


def no_color() -> bool:
    """NO_COLOR=1 时全部退回 dim/bold 表达层级 —— 那套本来就够用。"""
    return bool(os.environ.get("NO_COLOR"))


# ---- 语义样式 --------------------------------------------------------------
# 这几个常量给 rich 的 Text(style=...) 用。**不能写 `$accent` 那种 Textual 变量** ——
# 变量替换只发生在 content markup 里,rich 自己解析样式名时不认识 `$`。
#
# 分三层,直接对应 identity.md §3 从立绘里读出来的规律:
#
#   白 / 亮白   静止的、有形的部分   → 结构:分隔线、标签、工具名
#   藏青 / 冷青 压住画面的重量        → 层级:次级文字、gutter
#   粉          全部都在动           → 运动:流式游标、呼吸点、running、当前行
#
# 之前的版本只实现了最后一条,把前两层全做成了灰 dim —— 结果静止界面零颜色。
# NO_COLOR 下才退回纯 dim/bold:层级本来就建在排版和符号上,颜色只是加强。

_MONO = no_color()

def _c(color: str, mono: str = "dim") -> str:
    return mono if _MONO else color

MOTION_HEX = MOTION      # 粉:头发、飘带 —— 渐变起点
GLOW_HEX   = "#7FC8DC"   # 冷青:腿部与飘带边缘的辉光
STRUCT_HEX = "#5F7BA6"   # 藏青:裙摆、胸甲 —— 渐变终点

S_DIM     = "dim"
S_STRUCT  = _c(STRUCT_HEX)            # 藏青:gutter 竖线、结构线 —— 静止但有色
S_LABEL   = _c("#8FA8C4")            # 冷青偏白:工具名、字段标签
S_GLOW    = _c(GLOW_HEX)            # 冷青微光:极弱的辅助,用得很省
S_MOTION  = _c(MOTION)               # 粉 = 正在动
S_ERROR   = _c("#D96A72", "bold")
S_WARN    = _c("#D9B86A", "bold")
S_ADD     = _c("#8CBF9E")            # diff 的 + —— 唯一一处在错误之外用语义色

APP_CSS = """
Screen { background: $background; }

/* ── lazygit 式栅格:左侧四个面板 + 右侧 content/input ── */
#body { height: 1fr; }
#side  { width: 34; height: 1fr; }
#aside { width: 32; height: 1fr; }
#main { width: 1fr; height: 1fr; }

/* 面板 = 有名字的房间。标题嵌边框左上,计数嵌边框右下。
   焦点面板边框变粉 —— 全屏永远只有一处是"活的"。 */
.panel {
    border: round $secondary;
    border-title-color: $secondary;
    border-subtitle-color: $secondary;
    padding: 0 1;
    background: $background;
    overflow-y: auto;
    scrollbar-size-vertical: 1;
}
.panel:focus, .panel.-active {
    border: round $primary;
    border-title-color: $primary;
    border-subtitle-color: $primary;
}

#p-status   { height: 6; }   /* 4 行内容:3 行文字 + 1 行留给电子故障的竖条 */
#p-tasks    { height: 2fr; }   /* 右栏:当前进度最该看得全 */
#p-mcp      { height: 1fr; }
#p-skills   { height: 1fr; }
#p-sessions { height: 1fr; }
#p-thinking { height: 2fr; }   /* 跑起来之后这里最有信息量 */

/* 只有内层 #content-body 负责滚动。外层再开一次 overflow 会两层打架:
   内容被裁掉一半,挂进去的权限面板也会落在看不见的区域 → 按不到键 → 卡死。 */
#content { height: 1fr; overflow: hidden; }
/* 空态要撑满内容区,否则 renderable 拿到的 height 是 None,垂直居中算不出来 */
#splash { height: 1fr; }
#content-body { height: 1fr; padding: 0 1; }

/* 输入区:自己就是一个房间,所以"看不出哪里能输入"这个问题不存在了 */
#input-panel { height: 3; }
#goal { background: $background; border: none; padding: 0; height: 1; }
#goal:focus { border: none; }

/* 底部键位提示 —— lazygit 的常驻契约行 */
#hints { dock: bottom; height: 1; color: $secondary; padding: 0 1; }

/* content 区里的东西 */
.answer { padding: 0; color: $text; height: auto; }
.answer.-narration { color: $text-muted; }
.user   { padding: 1 0 0 0; color: $text; text-style: bold; height: auto; }
.gap    { height: 1; }
.about  { height: auto; padding: 1 0 0 2; }
"""
