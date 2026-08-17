"""`/about` 的字符画与版式测试。

字符画一旦出错,症状是"图整个散架",肉眼一看就知道 —— 但**在 CI 上没人看**。
所以测的都是不看图也能判定的事:

  1. **文件真的被打进包了** —— 它存在包目录而不是 `assets/`(sdist 排除了后者),
     这条约束只有测试能守住;有人把它挪回去的话这里会红
  2. **no_wrap 必须开** —— 字符画每行的长度就是构图,折行 = 散架
  3. **版式几何** —— 画和框不重叠、同高、窄屏退场。这几件坏了都不抛异常,
     只会静默变丑
"""
from aemeathcode.tui import splash


def test_portrait_loads_from_package() -> None:
    """能从包里读出来。

    读不到通常意味着打包配置把 art/ 漏了 —— 那是装完才炸的错,必须在这里拦住。
    """
    art = splash.portrait()
    assert art.plain.strip(), "字符画是空的"


def test_portrait_never_wraps() -> None:
    """no_wrap 是构图的一部分,不是可选优化。"""
    art = splash.portrait()
    assert art.no_wrap is True
    assert art.overflow == "crop"


def test_portrait_fits_declared_width() -> None:
    """所有行都在 90 列内 —— 生成时定死的宽度,超了说明源文件被手改坏了。"""
    lines = splash.portrait().plain.splitlines()
    assert lines, "没有行"
    assert max(len(line) for line in lines) <= 90


# ---- /about 的横排版式 ----


async def _about_regions(width: int, height: int) -> dict[str, tuple[int, int, int, int]]:
    """跑一遍 /about,返回各块的 (x, y, w, h)。"""
    from aemeathcode.tui.app import AemeathApp

    app = AemeathApp()
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        app._model, app._session_id, app._window = "m", "59f3f72e", 1000
        await app._show_about()
        await pilot.pause()
        out = {}
        for cls in (".about-art", ".about-col", ".about-slot"):
            found = app.query(cls)
            if found:
                r = found.first().region
                out[cls] = (r.x, r.y, r.width, r.height)
        return out


async def test_about_is_side_by_side_when_wide() -> None:
    """够宽时画在左、框在右,且**不重叠** —— 重叠意味着文字被画压住。"""
    r = await _about_regions(250, 60)
    assert ".about-art" in r, "宽终端下应该画"
    ax, _, aw, _ = r[".about-art"]
    cx, _, _, _ = r[".about-col"]
    assert cx >= ax + aw, f"框 x={cx} 压在画上(画右边界 {ax + aw})"


async def test_about_text_is_vertically_centred() -> None:
    """文字块对着画的中线。

    没有边框,这块**全靠位置**成立 —— 位置错了就是飘在旁边的几行字。
    实现依赖 `.about-slot` 那层壳;壳被当成冗余删掉的话这条会红。
    """
    r = await _about_regions(250, 60)
    _, ay, _, ah = r[".about-art"]
    _, cy, _, ch = r[".about-col"]
    assert abs((cy + ch / 2) - (ay + ah / 2)) <= 1, "文字块没对上画的中线"


async def test_about_drops_art_when_narrow() -> None:
    """窄了就不画。裁掉半张脸比没有更糟,所以是"藏"不是"缩"。"""
    r = await _about_regions(150, 60)
    assert ".about-art" not in r
    assert ".about-slot" not in r, "没画的时候不该有横排的壳"


async def _rendered_text(width: int, height: int = 60) -> str:
    """把整屏渲染成纯文本(经 SVG 快照),用来检查有没有被静默裁掉的内容。"""
    import re

    from aemeathcode.tui.app import AemeathApp

    app = AemeathApp()
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        app._model, app._session_id, app._window = "deepseek-v4-flash", "709407b0", 1000000
        await app._show_about()
        await pilot.pause()
        return "".join(re.findall(r">([^<>]*)</text>", app.export_screenshot()))


async def test_about_text_is_never_clipped() -> None:
    """元信息**一个字都不能被裁掉**。

    这条守的是一个真出过的 bug:文字栏原本是 `width: auto`,死要 53 列,
    终端窄于 214 列时右边就被容器边界**静默裁掉**几个字 —— 不报错、不折行、
    几何断言也查不出来(widget 报的是请求尺寸,不是可见范围)。
    改成 `1fr` 之后它会折行而不是丢字。

    只测阈值刚过线那一档 —— 画还在、空间最紧,那里最容易翻车。
    """
    from aemeathcode.tui.app import ABOUT_ART_MIN_WIDTH

    # content-body 宽 = 终端列数 - 72(两侧栏 66 + #content 边框与 padding 4
    # + #content-body 自己的 padding 2)。+72 正好落在阈值上,画一定在。
    cols = ABOUT_ART_MIN_WIDTH + 72
    regions = await _about_regions(cols, 60)
    assert ".about-art" in regions, f"{cols} 列下画应该还在,否则这条测试测了个寂寞"

    text = await _rendered_text(cols)
    for word in ("Runtime", "Agent", "Coding", "deepseek-v4-flash", "1000000"):
        assert word in text, f"{word!r} 被裁掉了"
