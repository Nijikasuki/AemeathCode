"""台账排版层的单元测试。

重点测三件在真机上最容易崩、又最难靠肉眼发现的事:
  1. **宽度按显示格算,不按 len() 算** —— CJK 一个字占两格,算错就整列错位
  2. **四档窄屏降级** —— 每一档的 chrome 宽度和内容宽度
  3. **工具输出 → 一个量化事实** —— 各工具的 metric 提炼
"""
import pytest
from rich.console import Console

from aemeathcode.tui.ledger import CONTENT_MAX, LedgerRow, fit, geometry, pad_to
from aemeathcode.tui.widgets import (
    ToolCall,
    humanize,
    is_readonly,
    metric_of,
    target_of,
)


def render(renderable, width: int) -> list[str]:
    """把 renderable 渲染成纯文本行(去掉行尾空白)。"""
    console = Console(width=width, force_terminal=False, legacy_windows=False)
    with console.capture() as cap:
        console.print(renderable, end="")
    return [line.rstrip() for line in cap.get().splitlines()]


# ---- 宽度:显示格 vs 字符数 ----

def test_fit_按显示格截断而不是字符数():
    # 8 个 CJK = 16 格。限 10 格只能放 4 个字 + 省略号
    assert fit("一二三四五六七八", 10) == "一二三四…"
    assert fit("abcdefgh", 10) == "abcdefgh"       # 没超就不动
    assert fit("", 10) == ""
    assert fit("一二三", 0) == ""


def test_pad_to_按显示格补齐():
    assert len(pad_to("中文", 10)) == 10 - 2       # 2 个 CJK 占 4 格,只补 6 个空格
    assert pad_to("ab", 5) == "ab   "


# ---- 四档降级 ----

@pytest.mark.parametrize("width,chrome,gutter,rule,labels", [
    (250, 12, 8, True, True),      # 宽终端
    (120, 12, 8, True, True),
    (100, 12, 8, True, True),      # 边界
    (99, 8, 4, True, False),       # 降一档:step 号消失
    (70, 8, 4, True, False),
    (69, 4, 2, False, False),      # 再降:竖线消失
    (50, 4, 2, False, False),
    (49, 3, 1, False, False),      # 最窄:只剩符号
    (30, 3, 1, False, False),
])
def test_四档几何(width, chrome, gutter, rule, labels):
    geo = geometry(width)
    assert (geo.chrome, geo.gutter_w, geo.rule, geo.labels) == (chrome, gutter, rule, labels)


def test_内容区吃满可用宽度():
    """多面板布局下,面板边框已经限过宽了,内容区不该再卡一次 ——
    再卡一次的结果是面板右半边空着(单栏时代那个 96 的上限是错的迁移)。"""
    assert geometry(250).content_w == 250 - 12
    assert geometry(60).content_w == 60 - 4
    assert CONTENT_MAX >= 400


def test_窄屏丢标签保符号():
    """`step 3` 这种标签在窄屏第一个被丢掉,符号永远留着 —— 它承载语义。"""
    assert "step 3" in render(LedgerRow("step 3", "内容", is_symbol=False), 120)[0]
    assert "step 3" not in render(LedgerRow("step 3", "内容", is_symbol=False), 80)[0]
    assert "◇" in render(LedgerRow("◇", "内容"), 80)[0]
    assert "◇" in render(LedgerRow("◇", "内容"), 40)[0]


# ---- LedgerRow 排版 ----

def test_gutter_右对齐且内容起始列固定():
    lines = render(LedgerRow("◇", "read_file"), 120)
    assert lines[0].index("│") == 10        # 1 空格 + 8 gutter + 1 空格
    assert lines[0].index("read_file") == 12


def test_换行时续行留空_gutter_但竖线继续():
    """一条竖直基线贯穿全屏,连发几十次 tool call 视觉上也不会晃。"""
    lines = render(LedgerRow("◇", "词 " * 80), 120)
    assert len(lines) > 1
    assert lines[0].lstrip().startswith("◇")
    assert lines[1].index("│") == 10        # 续行竖线对齐
    assert "◇" not in lines[1]              # 续行不重复符号


def test_metric_右对齐在内容区边界():
    lines = render(LedgerRow("◇", "read_file  a.py", "88 行"), 120)
    assert lines[0].endswith("88 行")
    # 贴内容区右边界(12 + 96),不是贴屏幕右边界 120
    assert len(lines[0]) <= 12 + CONTENT_MAX


def test_空行只有竖线():
    assert render(LedgerRow("", ""), 120)[0].strip() == "│"


# ---- 工具行的内容提炼 ----

def test_target_取最该被看见的那个参数():
    """字段名是给机器看的 —— 旧版把整个 params JSON 回显出来。"""
    assert target_of("read_file", {"path": "a/b.py"}) == "a/b.py"
    assert target_of("bash", {"command": "ls -la"}) == "ls -la"
    assert target_of("spawn_agent", {"goal": "统计"}) == "统计"
    assert target_of("unknown", {"x": 1}) == '{"x": 1}'
    assert target_of("noop", {}) == ""


@pytest.mark.parametrize("tool,content,expected", [
    ("list_dir", "[FILE] a\n[DIR] b", "2 项"),
    ("list_dir", "目录为空", "空"),
    ("read_file", "l1\nl2\nl3", "3 行"),
    ("read_file", "单行", ""),                       # 一行没什么好说的
    ("bash", "stdout:a\nb", "2 行"),
    ("write_file", "已写入 128 字节 → /tmp/a", "128 字节"),
])
def test_metric_每个工具提炼一个量化事实(tool, content, expected):
    assert metric_of(tool, content, is_error=False) == expected


def test_失败时不出_metric():
    assert metric_of("read_file", "错误:文件不存在", is_error=True) == ""


def test_只读工具可折叠_改变世界的工具不可():
    assert is_readonly("read_file") and is_readonly("list_dir")
    assert is_readonly("search_repositories")        # MCP 前缀启发式
    assert not is_readonly("bash")
    assert not is_readonly("write_file")
    assert not is_readonly("spawn_agent")
    assert not is_readonly("some_mcp_thing")         # 判不出来 → 单独显示,宁可啰嗦不可隐瞒


def test_bash_失败输出整理成人话():
    raw = "stdout:,stderr:ls: cannot access 'x': No such file or directory,returncode:2"
    out = humanize("bash", raw)
    assert "No such file" in out
    assert "退出码 2" in out
    assert "returncode" not in out
    # 拆不开就原样返回,不丢信息
    assert humanize("bash", "乱七八糟") == "乱七八糟"
    assert humanize("read_file", "原样") == "原样"


def test_toolcall_符号随状态变():
    call = ToolCall(name="read_file", params={"path": "a"})
    assert call.symbol == "◌"                        # 进行中
    call.finished = True
    assert call.symbol == "◇"                        # 只读完成
    call.is_error = True
    assert call.symbol == "×"                        # 失败换符号,不是只换颜色
    write = ToolCall(name="bash", params={"command": "x"}, finished=True)
    assert write.symbol == "◆"                       # 改变世界的工具


# ---- 空态 / wordmark ----

def test_wordmark_逐字母上色且粉为主体():
    """opencode 的做法:整个字母一个深浅,不是逐字符渐变(那样会糊成一片灰紫)。

    断言:字母数 == 7(AEMEATH),前半偏粉、末尾沉到藏青。
    """
    from aemeathcode.tui.splash import WORDMARK, _letter_color, _letter_spans

    spans = _letter_spans(WORDMARK)
    assert len(spans) == 7, f"AEMEATH 应该切出 7 个字母,实际 {len(spans)}"

    from rich.color import Color
    triplets = [Color.parse(_letter_color(i, 7)).triplet for i in range(7)]
    assert all(t.red > t.blue for t in triplets[:4]), "前四个字母应该是粉色主体"
    assert triplets[-1].blue > triplets[-1].red, "最后一个字母应该沉到藏青"
    assert triplets[0].red > triplets[-1].red, "红色分量自左向右递减"


def test_空态四个变体都能渲染且不为空():
    from aemeathcode.tui import splash

    for name in ("full", "stars", "line", "core"):
        lines = render(splash.make(name), 100)
        assert any(line.strip() for line in lines), name


# ---- 框架命名碰撞的护栏 ----

def test_不许覆盖_textual_基类的私有成员():
    """踩过两次的坑,做成自动挡。

    1. `ToolGroup._closed` 撞了 `MessagePump._closed` —— Textual 的消息泵主循环就是
       `while not self._closed`,一置 True 那个 widget 的消息泵直接退出并自我 detach。
       没有异常、没有 remove()、没有 _prune(),任何探针都抓不到。
    2. `ThinkingPanel._render()` 撞了 `Widget._render()` —— 渲染管线拿到 None 直接崩。

    这类 bug 的共同点是**症状离原因很远**,所以宁可用一条呆板的测试挡住。

    用 AST 只扫**我自己源码里写的**名字 —— Textual 的元类会给每个子类注入
    `_reactives` / `_css_type_name` 之类的属性,那些不算覆盖。
    """
    import ast
    import importlib
    import inspect
    from pathlib import Path

    # 有意实现的 Textual 生命周期钩子和框架约定的类属性,允许同名
    ALLOWED = {
        "render", "compose", "on_mount", "on_click", "on_key", "on_event",
        "DEFAULT_CSS", "BINDINGS", "CSS", "can_focus",
        "elements",                # rich Markdown 的扩展点,就是拿来覆盖的
        "ENABLE_COMMAND_PALETTE",  # Textual 有意暴露的开关(我们关掉它腾出 ctrl+p)

    }

    offenders = []
    for mod_name in ("ledger", "widgets", "panels", "splash", "markdown", "app"):
        module = importlib.import_module(f"aemeathcode.tui.{mod_name}")
        tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            cls = getattr(module, node.name, None)
            if cls is None:
                continue
            written = {
                child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                else child.target.id if isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
                else None
                for child in node.body
            }
            for child in node.body:          # 普通赋值
                if isinstance(child, ast.Assign):
                    written.update(t.id for t in child.targets if isinstance(t, ast.Name))
            for name in written - {None}:
                if name in ALLOWED or name.startswith("__"):
                    continue
                if any(name in vars(base) for base in cls.__mro__[1:]):
                    offenders.append(f"{cls.__name__}.{name}")

    assert not offenders, f"覆盖了 Textual/Rich 基类的成员,换个名字: {offenders}"
