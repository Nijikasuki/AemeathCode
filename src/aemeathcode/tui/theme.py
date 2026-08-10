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

# ---- 调色板 ----------------------------------------------------------------
# 三轮才落到这个位置,两个失败的极端都记下来,省得以后重来:
#
#   ① 九个面板各取渐变上的一点 → 九种颜色 → **游戏 HUD,不是工具**
#   ② 全部收敛成同一个暗灰紫 + 纯黑底 → **整屏没对比,"这个也太黑了吧"**
#
# 落点:**颜色承担结构含义** —— 三栏三色,编码"你在哪一栏";三种色全部取自 logo
# 那条色带,所以彩而不花。底色不用纯黑(纯黑配暗边框会糊成一片)。

BG        = "#0E0D14"
SURFACE   = "#15141D"
MUTED     = "#6D82A4"   # 次级文字、gutter、竖线 —— 这些不跟着分栏变色
TEXT      = "#E4E1EC"

# 品牌色 —— 只出现在 logo 的渐变里,以及 focus / 状态
PINK = "#FF9ED8"
CYAN = "#7DE8E8"
IRIS = "#9B8CFF"

MOTION = PINK           # 正在动的东西:流式游标、running、`›` 提示符

# **三栏三色 —— 颜色承担结构含义,而不是装饰。**
# 试过两个极端都不行:九个面板九种渐变色 = 游戏 HUD;全部统一一个暗灰紫 = 太黑没对比。
# 落点是让颜色**编码"你在哪一栏"**:一眼扫过去就知道左中右三个区域的边界在哪,
# 而三种色又全部来自 logo 那条色带,所以整体仍然是同一个品牌。
COL_LEFT   = IRIS       # 左栏:Status / Sessions / Thinking
COL_MAIN   = CYAN       # 中栏:Content / 输入
COL_RIGHT  = PINK       # 右栏:Tasks / Changes / MCP / Skills


def _lerp(a: str, b: str, t: float) -> str:
    t = max(0.0, min(t, 1.0))
    ca = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    cb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


AEMEATH_THEME = Theme(
    name="aemeath",
    primary=PINK,          # focus / running,仅此
    secondary=IRIS,        # 兜底边框色(具体面板由 app 按栏覆盖)
    accent=PINK,
    foreground=TEXT,
    background=BG,
    surface=SURFACE,
    panel=SURFACE,
    success=CYAN,          # 只给真正的成功语义,不当装饰
    warning="#D4B26B",
    error="#E07A88",
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

MOTION_HEX = PINK   # logo 渐变起点
GLOW_HEX   = CYAN   # 中段
STRUCT_HEX = IRIS   # 终点

S_DIM     = "dim"
S_STRUCT  = _c(MUTED)            # 藏青:gutter 竖线、结构线 —— 静止但有色
S_LABEL   = _c(MUTED)            # 冷青偏白:工具名、字段标签
S_GLOW    = _c(MUTED)      # 曾经的"辅助光",现在退回中性 —— 它不承载语义            # 冷青微光:极弱的辅助,用得很省
S_MOTION  = _c(PINK)               # 粉 = 正在动
S_ERROR   = _c("#E07A88", "bold")
S_WARN    = _c("#D4B26B", "bold")
S_ADD     = _c("#7FB093")  # diff 的 +,低饱和绿,不抢戏            # diff 的 + —— 唯一一处在错误之外用语义色

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
    border-title-color: $text-muted;
    border-subtitle-color: $text-muted;
    padding: 0 1;
    background: $background;
    overflow-y: auto;
    scrollbar-size-vertical: 1;
}
/* 焦点/激活的面板抢回粉色 —— 全屏永远只有一处是"活的",它不参与渐变 */
.panel:focus, .panel.-active {
    border: round $primary;
    border-title-color: $primary;
    border-subtitle-color: $primary;
}

#p-status   { height: 6; }   /* 4 行内容:3 行文字 + 1 行留给电子故障的竖条 */
#p-tasks    { height: 2fr; }   /* 右栏:当前进度最该看得全 */
#p-changes  { height: 1fr; }
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
#hints { dock: bottom; height: 1; color: $text-muted; padding: 0 1; }

/* content 区里的东西 */
.answer { padding: 0; color: $text; height: auto; }
.answer.-narration { color: $text-muted; }
.user   { padding: 1 0 0 0; color: $text; text-style: bold; height: auto; }
.gap    { height: 1; }
.about  { height: auto; padding: 1 0 0 2; }
"""
