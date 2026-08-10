"""空态 —— 什么都还没发生时,屏幕上该有什么。

为什么需要它:删掉旧 banner 之后,250×70 的终端剩下一片纯黑加两个灰字,
观感是"是不是没启动起来"。identity.md §2 那条"空闲时界面不是死的"没被满足。

三条约束(它们把"装饰"和"空态设计"区分开):
  * **不是 logo** —— 不画名字的像素字、不画立绘、不需要认识这个角色才看得懂
  * **不占信息位** —— 一有内容进来它就该退场,不跟内容抢
  * **静止时也有色** —— 粉蓝白三层同时在场(见 theme.py 的分层说明)
"""
from __future__ import annotations

import random

from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, RenderResult
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

from aemeathcode.tui.theme import (
    GLOW_HEX,
    MOTION_HEX,
    S_GLOW,
    S_MOTION,
    S_STRUCT,
    STRUCT_HEX,
)

TAGLINE = "远航星"

# opencode 那种实心块字形:笔画粗、方、没有描边缝隙。
# 每个字母用 `▄▀█` 拼实心块,字母之间空一列。
WORDMARK = (
    "▄▀▀▄ ▄▀▀▀ █▄ ▄█ ▄▀▀▀ ▄▀▀▄ ▀▀█▀▀ █  █",
    "█▄▄█ █▀▀  █ ▀ █ █▀▀  █▄▄█   █   █▄▄█",
    "█  █ ▀▄▄▄ █   █ ▀▄▄▄ █  █   █   █  █",
)

WORDMARK_SMALL = (
    "▄▀█ █▀▀ █▀▄▀█ █▀▀ ▄▀█ ▀█▀ █ █",
    "█▀█ ██▄ █ ▀ █ ██▄ █▀█  █  █▀█",
)

VERSION = "v0.2.1"


def _lerp(a: str, b: str, t: float) -> str:
    """两个 hex 颜色之间线性插值。"""
    t = max(0.0, min(t, 1.0))
    ca = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    cb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def _letter_spans(rows: tuple[str, ...]) -> list[tuple[int, int]]:
    """按"整列都是空格"切出每个字母的列区间。"""
    w = len(rows[0])
    blank = [all(r[x] == " " for r in rows) for x in range(w)]
    spans, start = [], None
    for x in range(w):
        if not blank[x] and start is None:
            start = x
        elif blank[x] and start is not None:
            spans.append((start, x)); start = None
    if start is not None:
        spans.append((start, w))
    return spans


# 流光:一条亮带扫过 logo,扫完停一拍再来。
# 这是 identity.md「有心跳的机器 / 波动爱心」那条的落地 —— 持续、周期、柔和的脉冲。
# 参考素材是角色肩后那团一张一缩的辉光。
SHEEN_HEX = "#FFFFFF"      # 亮带的顶点:白,不是粉 —— 光本身没有颜色
SWEEP_SPAN = 2.6           # 扫一遍要几个"相位单位"
SWEEP_PAUSE = 1.8          # 扫完停多久再来


def _letter_color(i: int, n: int, phase: float | None = None) -> str:
    """逐**字母**取色 —— opencode 的做法。整个字母一个深浅,比逐字符渐变更有形。

    粉占前 2/3(她的头发),后段沉向藏青(裙摆)。幂曲线偏置保证粉是主体。

    `phase` 非 None 时叠加流光:亮带中心附近的字母被推向白,离得越远越接近本色。
    """
    t = (i / max(n - 1, 1)) ** 3.0          # 幂曲线:前面几个字母几乎不动
    if t < 0.72:
        # 前段只走到冷青的一半 —— 粉必须是主体,不能五五开(五五开会糊成灰紫)
        base = _lerp(MOTION_HEX, GLOW_HEX, t / 0.72 * 0.5)
    else:
        base = _lerp(GLOW_HEX, STRUCT_HEX, (t - 0.72) / 0.28)
    if phase is None:
        return base
    cycle = SWEEP_SPAN + SWEEP_PAUSE
    head = (phase % cycle) / SWEEP_SPAN * (n + 1) - 0.5     # 亮带中心,扫完就跑出右边界
    d = abs(i / max(n - 1, 1) * n - head)
    glow = max(0.0, 1.0 - (d / 1.3) ** 2)                   # 柔和衰减,不是硬边
    return _lerp(base, SHEEN_HEX, glow * 0.75)


class Wordmark:
    """AEMEATH 的 block logo —— **粉色为主体**,逐字符渐变到藏青。

    两个关键点(上一版都做错了):

    1. **按字符格插值,不按行。**只有 5 行的话,按行上色就只有 5 个色阶,
       眼睛直接读成"上粉下青"两条色带。加一个横向分量,相邻格子颜色都不同,
       才会读成连续的渐变。
    2. **幂曲线偏置。**线性插值的中点是灰紫(粉蓝调和色),糊成一片谁也不是。
       t ** 1.7 把大部分格子压在粉这一端,藏青只在右下角收尾 ——
       对应立绘:粉发占大面积,藏青裙摆压在下方一角。
    """

    BIAS = 1.7          # 越大,粉占的面积越大
    HORIZ = 0.34        # 横向分量权重(制造平滑,不喧宾夺主)

    def __init__(self, phase: float | None = None) -> None:
        self.phase = phase

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        big = options.max_width >= len(WORDMARK[0]) + 4
        rows = WORDMARK if big else WORDMARK_SMALL
        spans = _letter_spans(rows)
        for text in rows:
            yield Segment("  ")
            for x, ch in enumerate(text):
                idx = next((i for i, (a, b) in enumerate(spans) if a <= x < b), None)
                style = Style(color=_letter_color(idx, len(spans))) if idx is not None else None
                yield Segment(ch, style)
            yield Segment("\n")


class Starfield:
    """稀疏星点 —— "长航的星辉"。

    粉蓝两色的极暗点阵,密度很低(约每 55 个字符格一颗)。用固定种子生成,
    所以它不会每帧抖动 —— 是"一片安静的星野",不是噪声。
    """

    def __init__(self, seed: int = 0x4145, density: int = 34, top: int = 0) -> None:
        self._seed = seed
        self._density = density
        self._top = top          # 上方留给标题的行数

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        height = options.height or 20
        rng = random.Random(self._seed)
        pink = console.get_style(S_MOTION, default="")
        blue = console.get_style(S_STRUCT, default="")
        glow = console.get_style(S_GLOW, default="")
        # 三种亮度的点:大部分是最暗的那种
        palette = [(Style(color=blue.color, dim=True), "·")] * 5 + \
                  [(Style(color=glow.color, dim=True), "·")] * 3 + \
                  [(Style(color=pink.color, dim=True), "·")] * 2 + \
                  [(Style(color=pink.color), "✦")]

        for _ in range(max(height - self._top, 0)):
            col = 0
            row: list[Segment] = []
            while col < width:
                gap = rng.randint(self._density // 2, self._density * 2)
                if col + gap >= width:
                    break
                row.append(Segment(" " * gap))
                style, ch = palette[rng.randrange(len(palette))]
                row.append(Segment(ch, style))
                col += gap + 1
            yield from row
            yield Segment("\n")


class Horizon:
    """一条粉→蓝的细线 + 名字。像地平线上的一道微光。"""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = min(options.max_width - 4, 64)
        pink = console.get_style(S_MOTION, default="")
        blue = console.get_style(S_STRUCT, default="")
        glow = console.get_style(S_GLOW, default="")
        yield Segment("\n")
        yield Segment("  ")
        # 粉 → 冷青 → 藏青,三段渐变
        for i, style in enumerate((pink, glow, blue)):
            seg = width // 3
            yield Segment("╌" * seg, Style(color=style.color, dim=(i > 0)))
        yield Segment("\n\n")
        line = Text("  AEMEATH", style=Style(color=pink.color))
        line.append("   ")
        line.append(TAGLINE, style=Style(color=blue.color, dim=True))
        yield line
        yield Segment("\n")


class Core:
    """屏幕上只有一个粉色的点在呼吸 —— 波动爱心,能量核心。极简到底。"""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        height = max((options.height or 20) // 2, 2)
        pink = console.get_style(S_MOTION, default="")
        blue = console.get_style(S_STRUCT, default="")
        yield Segment("\n" * height)
        pad = " " * max(options.max_width // 2 - 6, 2)
        yield Segment(pad)
        yield Segment("✦", Style(color=pink.color))
        yield Segment("\n\n")
        yield Segment(pad)
        yield Segment(TAGLINE, Style(color=blue.color, dim=True))
        yield Segment("\n")


# 空态里列出的命令 —— opencode 那种"logo 在中间,下面是能敲什么"
SPLASH_COMMANDS = (
    ("/resume", "恢复会话"),
    ("/clear", "开新会话"),
    ("/mcp", "MCP server"),
    ("/usage", "本会话累计 token"),
    ("^q", "退出"),
)


class Splash:
    """默认空态:logo 居中 + 下面列出可用命令。

    居中是自己算的,不是靠 CSS —— 因为要同时按 logo 和命令表的**总高度**做垂直居中,
    Textual 的 content-align 只认单个 renderable。
    """

    def __init__(self, phase: float | None = None) -> None:
        self.phase = phase

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        big = width >= len(WORDMARK[0]) + 4
        rows = WORDMARK if big else WORDMARK_SMALL
        art_w = len(rows[0])
        # 命令表:两列(命令 + 说明),整体宽度按最长的那条算
        key_w = max(len(k) for k, _ in SPLASH_COMMANDS)
        cmd_w = key_w + 2 + max(cell_len(d) for _, d in SPLASH_COMMANDS)
        block_w = max(art_w, cmd_w, cell_len(TAGLINE))
        left = max((width - block_w) // 2, 0)

        total_h = len(rows) + 4 + len(SPLASH_COMMANDS) + 2
        top = max(((options.height or total_h) - total_h) // 2, 0)
        yield Segment("\n" * top)

        art_pad = " " * (left + max((block_w - art_w) // 2, 0))
        spans = _letter_spans(rows)
        for text in rows:
            yield Segment(art_pad)
            for x, ch in enumerate(text):
                idx = next((i for i, (a, b) in enumerate(spans) if a <= x < b), None)
                style = (Style(color=_letter_color(idx, len(spans), self.phase))
                         if idx is not None else None)
                yield Segment(ch, style)
            yield Segment("\n")

        blue = console.get_style(S_STRUCT, default="")
        glow = console.get_style(S_GLOW, default="")
        # 版本号紧跟 logo 右下 —— opencode 就是这么放的
        yield Segment(" " * (left + max(block_w - cell_len(VERSION), 0)))
        yield Segment(VERSION, Style(color=blue.color, dim=True))
        yield Segment("\n\n")
        yield Segment(" " * (left + max((block_w - cell_len(TAGLINE)) // 2, 0)))
        yield Segment(TAGLINE, Style(color=blue.color, dim=True))
        yield Segment("\n\n")

        for key, desc in SPLASH_COMMANDS:
            yield Segment(" " * (left + max((block_w - cmd_w) // 2, 0)))
            yield Segment(key.ljust(key_w + 2), Style(color=glow.color))
            yield Segment(desc, Style(color=blue.color, dim=True))
            yield Segment("\n")


class SplashStars(Splash):
    """logo + 命令表,底下再铺一片星野。"""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield from Splash.__rich_console__(self, console, options)
        yield from Starfield(top=6).__rich_console__(console, options)


VARIANTS = {
    "full": Splash,          # wordmark + tagline(默认,紧凑)
    "stars": SplashStars,    # wordmark + 星野铺满空屏
    "line": Horizon,         # 只有渐变细线 + 名字,最克制
    "core": Core,            # 屏幕中央一个呼吸点,极简
}


def make(name: str = "full", phase: float | None = None):
    """AEMEATH_SPLASH=full|stars|line|core|none 切换;none 由调用方处理。"""
    cls = VARIANTS.get(name, Splash)
    try:
        return cls(phase)
    except TypeError:          # Horizon / Core 不吃 phase
        return cls()
