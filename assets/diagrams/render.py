"""把 assets/diagrams/*.mmd 渲染成静态 SVG(README 里引用的就是这些 SVG)。

**为什么不直接在 README 里写 mermaid 代码块:**
GitHub 会给渲染出来的 mermaid 图挂一条缩放/平移控制栏,常驻不消失,而且会盖住
图右上角的节点。静态图片没有这个问题。

**为什么不用 mermaid-cli:**
1. 它依赖 Chromium,本机装不上;
2. 更要命的是它默认用 `<foreignObject>` 装节点标签 —— 那东西在被 `<img>` 加载的
   SVG 里不渲染(浏览器对 img-SVG 有安全限制)。所以这里只用 `<text>`。

**深浅色主题:**
节点给不透明底色,文字颜色由底色决定而不是由页面背景决定 —— 这样即使读者的
GitHub 主题和系统主题不一致(媒体查询按系统走),图也照样清楚。媒体查询命中时
再换成深色卡片,让它跟页面融为一体。

跑法:`make diagrams` 或 `uv run python assets/diagrams/render.py`
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).parent

FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', "
        "'PingFang SC', 'Microsoft YaHei', Helvetica, Arial, sans-serif")
FS = 14           # 字号
LH = 21           # 行高
PAD_X, PAD_Y = 20, 16   # 节点内边距
RANK_GAP = 92     # 两列之间的最小水平间距(边标签会撑大它)
ROW_GAP = 34      # 同一列内上下两个节点的间距
MARGIN = 14       # 画布外边距

# ---------------------------------------------------------------- 解析 .mmd
# 只认这份项目里实际用到的那点语法,不是通用 mermaid 解析器。
NODE_RE = re.compile(r'(\w+)(\[|\(\[)"([^"]*)"(\]\)|\])')
EDGE_RE = re.compile(r'(\w+)\s*(<-->|-\.->|-->)\s*(?:\|"([^"]*)"\|\s*)?(\w+)')
CLASS_RE = re.compile(r'^\s*class\s+([\w,]+)\s+(\w+)\s*$')


def parse(text: str):
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    roles: dict[str, str] = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("flowchart", "classDef", "%%")):
            if m := CLASS_RE.match(raw):
                for nid in m.group(1).split(","):
                    roles[nid.strip()] = m.group(2)
            continue
        if m := CLASS_RE.match(raw):
            for nid in m.group(1).split(","):
                roles[nid.strip()] = m.group(2)
            continue

        for m in NODE_RE.finditer(line):
            nid, open_, label = m.group(1), m.group(2), m.group(3)
            nodes.setdefault(nid, {
                "id": nid,
                "lines": label.split("<br/>"),
                "stadium": open_ == "([",       # (["文字"]) 画成胶囊
            })
        # 去掉节点定义再找边,免得标签里的字符干扰
        for m in EDGE_RE.finditer(NODE_RE.sub(r"\1", line)):
            src, arrow, elabel, dst = m.group(1), m.group(2), m.group(3), m.group(4)
            edges.append({"src": src, "dst": dst, "label": elabel or "",
                          "both": arrow == "<-->", "dashed": arrow == "-.->"})

    for nid in nodes:
        nodes[nid]["role"] = roles.get(nid, "box")
    return nodes, edges


# ---------------------------------------------------------------- 文字量宽
def text_w(s: str, size: int = FS) -> float:
    """估算字符串宽度。宁可估宽 —— 估窄了文字会溢出框,估宽了只是留白多一点。"""
    w = 0.0
    for ch in s:
        if ord(ch) >= 0x2E80:        # CJK / 全角
            w += size * 1.02
        elif ch in "·—…":
            w += size * 0.5
        elif ch in " .,'`|/:":
            w += size * 0.30
        elif ch.isupper():
            w += size * 0.66
        else:
            w += size * 0.58
    return w


# ---------------------------------------------------------------- 布局
def layout(nodes: dict, edges: list):
    for n in nodes.values():
        n["w"] = max(text_w(l) for l in n["lines"]) + PAD_X * 2
        n["h"] = len(n["lines"]) * LH + PAD_Y * 2

    # 分列:沿着边往右推,已经排过的节点不再改(否则回边会把列号顶飞)
    rank: dict[str, int] = {}
    for e in edges:
        rank.setdefault(e["src"], 0)
        if e["dst"] not in rank:
            rank[e["dst"]] = rank[e["src"]] + 1
    for nid in nodes:
        rank.setdefault(nid, 0)

    cols: dict[int, list[str]] = {}
    for nid, r in rank.items():
        cols.setdefault(r, []).append(nid)

    # 每条边横跨哪一段列间距。折线(两端不同行)要各占一条竖直"车道",
    # 否则几条边的标签会全挤在同一个 x 上叠成一坨。
    for e in edges:
        e["gap"] = min(rank[e["src"]], rank[e["dst"]])
    lanes: dict[int, list[dict]] = {}
    for e in edges:
        lanes.setdefault(e["gap"], []).append(e)
    for gap_i, group in lanes.items():
        elbows = [e for e in group if rank[e["src"]] != rank[e["dst"]]]
        for i, e in enumerate(elbows):
            e["frac"] = (i + 1) / (len(elbows) + 1)
        for e in group:                      # 同行往返:标签左右分开站
            if "frac" not in e:
                e["frac"] = 0.30 if rank[e["src"]] <= rank[e["dst"]] else 0.70

    # 每一列之间的间距:至少 RANK_GAP,车道多或标签长就撑开
    gap_after: dict[int, float] = {}
    for gap_i, group in lanes.items():
        labeled = [e for e in group if e["label"]]
        need = max([text_w(e["label"], 12) + 48 for e in labeled], default=0)
        # 折线标签停在各自竖直车道的中点,横向必须留够一整个标签的位置
        elbow_lbl = [e for e in labeled if rank[e["src"]] != rank[e["dst"]]]
        lanes_need = sum(text_w(e["label"], 12) + 34 for e in elbow_lbl)
        gap_after[gap_i] = max(RANK_GAP, need, lanes_need)

    x = MARGIN
    for r in sorted(cols):
        col_w = max(nodes[n]["w"] for n in cols[r])
        for nid in cols[r]:
            nodes[nid]["x"] = x + (col_w - nodes[nid]["w"]) / 2
        x += col_w + gap_after.get(r, RANK_GAP)
    width = x - gap_after.get(max(cols), RANK_GAP) + MARGIN

    # 每一列内部垂直居中堆叠
    height = MARGIN * 2 + max(
        sum(nodes[n]["h"] for n in c) + ROW_GAP * (len(c) - 1) for c in cols.values())
    for r in sorted(cols):
        col = cols[r]
        total = sum(nodes[n]["h"] for n in col) + ROW_GAP * (len(col) - 1)
        y = (height - total) / 2
        for nid in col:
            nodes[nid]["y"] = y
            y += nodes[nid]["h"] + ROW_GAP
    for n in nodes.values():
        n["cx"], n["cy"] = n["x"] + n["w"] / 2, n["y"] + n["h"] / 2

    # 接线槽位:同一个节点同一侧接了好几条边时,沿着这条边散开。
    # 不散的话,凡是连到同一个节点的边都会挤在 cy 上叠成一条 —— 往返两条边
    # 会看起来只有一条,方向信息就丢了。
    sides: dict[tuple[str, str], list] = {}
    for e in edges:
        back = rank[e["src"]] > rank[e["dst"]]
        e["left"], e["right"] = ((e["dst"], e["src"]) if back else (e["src"], e["dst"]))
        sides.setdefault((e["left"], "r"), []).append((e, "a"))
        sides.setdefault((e["right"], "l"), []).append((e, "b"))
    for (nid, _side), lst in sides.items():
        n, k = nodes[nid], len(lst)
        if k == 1:
            lst[0][0][f"off_{lst[0][1]}"] = 0.0
            continue
        # 按对端的高度排序,让线不互相交叉
        lst.sort(key=lambda p: nodes[p[0]["right"] if p[1] == "a" else p[0]["left"]]["cy"])
        step = min(n["h"] * 0.62 / (k - 1), 22)
        for i, (e, which) in enumerate(lst):
            e[f"off_{which}"] = (i - (k - 1) / 2) * step
    return width, height, rank


# ---------------------------------------------------------------- 画 SVG
STYLE = """
  .surface { fill: #f6f8fa; stroke: #8b93a7; stroke-width: 1.4; }
  .surface.accent { stroke: #d98cb3; stroke-width: 2; }
  .surface.soft   { stroke-dasharray: 5 4; }
  .t     { fill: #1f2328; font-size: %(fs)dpx; }
  .t.dim { fill: #57606a; font-size: 12px; }
  .edge  { stroke: #8b93a7; stroke-width: 1.4; fill: none; }
  .edge.dashed { stroke-dasharray: 5 4; }
  .chip  { fill: #f6f8fa; }
  .head  { fill: #8b93a7; }
  @media (prefers-color-scheme: dark) {
    .surface { fill: #161b22; stroke: #7d8590; }
    .surface.accent { stroke: #d98cb3; }
    .t     { fill: #e6edf3; }
    .t.dim { fill: #9198a1; }
    .edge  { stroke: #7d8590; }
    .chip  { fill: #161b22; }
    .head  { fill: #7d8590; }
  }
""" % {"fs": FS}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(nodes: dict, edges: list, width: float, height: float, rank: dict) -> str:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" font-family="{FONT}" '
        f'role="img">',
        f"<style>{STYLE}</style>",
        '<defs>',
        '<marker id="a" viewBox="0 0 10 8" refX="9" refY="4" markerWidth="8" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,4 L0,8 z" class="head"/></marker>',
        '</defs>',
    ]

    # ---- 边(先画,压在节点下面)
    for e in edges:
        s, d = nodes[e["src"]], nodes[e["dst"]]
        back = rank[e["src"]] > rank[e["dst"]]
        a, b = (d, s) if back else (s, d)          # a 在左,b 在右
        y1, y2 = a["cy"] + e["off_a"], b["cy"] + e["off_b"]
        x1, x2 = a["x"] + a["w"], b["x"]
        xm = x1 + (x2 - x1) * e["frac"]
        # 两端高度只差一点点(接线槽位错开造成的)就拉平,免得直线上多个小台阶
        if abs(y1 - y2) < 24:
            y1 = y2 = (y1 + y2) / 2
        elbow = abs(y1 - y2) > 2

        pts = ((x2, y2, x1, y1) if back else (x1, y1, x2, y2))
        path = (f"M{pts[0]:.0f},{pts[1]:.0f} H{xm:.0f} V{pts[3]:.0f} H{pts[2]:.0f}"
                if elbow else f"M{pts[0]:.0f},{pts[1]:.0f} H{pts[2]:.0f}")
        cls = "edge dashed" if e["dashed"] else "edge"
        head = ' marker-start="url(#a)"' if e["both"] else ""
        out.append(f'<path d="{path}" class="{cls}" marker-end="url(#a)"{head}/>')

        if e["label"]:
            lw = text_w(e["label"], 12)
            lx, ly = xm, ((y1 + y2) / 2 if elbow else y1)
            out.append(f'<rect class="chip" x="{lx - lw / 2 - 7:.0f}" y="{ly - 10:.0f}" '
                       f'width="{lw + 14:.0f}" height="20" rx="4"/>')
            out.append(f'<text class="t dim" x="{lx:.0f}" y="{ly:.0f}" '
                       f'text-anchor="middle" dominant-baseline="central">'
                       f'{esc(e["label"])}</text>')

    # ---- 节点
    for n in nodes.values():
        cls = "surface"
        if n["role"] in ("wire", "hot"):
            cls += " accent"
        elif n["role"] == "side":
            cls += " soft"
        rx = n["h"] / 2 if n["stadium"] else 7
        out.append(f'<rect class="{cls}" x="{n["x"]:.0f}" y="{n["y"]:.0f}" '
                   f'width="{n["w"]:.0f}" height="{n["h"]:.0f}" rx="{rx:.0f}"/>')
        top = n["cy"] - (len(n["lines"]) - 1) * LH / 2
        for i, line in enumerate(n["lines"]):
            out.append(f'<text class="t" x="{n["cx"]:.0f}" y="{top + i * LH:.0f}" '
                       f'text-anchor="middle" dominant-baseline="central">'
                       f'{esc(line)}</text>')

    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    for src in sorted(HERE.glob("*.mmd")):
        nodes, edges = parse(src.read_text(encoding="utf-8"))
        w, h, rank = layout(nodes, edges)
        svg = render(nodes, edges, w, h, rank)
        out = src.with_suffix(".svg")
        out.write_text(svg, encoding="utf-8")
        print(f"{out.name:24} {w:.0f} x {h:.0f}  ({len(nodes)} 节点 / {len(edges)} 边)")


if __name__ == "__main__":
    main()
