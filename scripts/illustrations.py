"""纯代码绘制公众号配图（内联 SVG，零外部依赖）。

合规要点（prompts/04_wechat_format.md）：
- 静态内联 SVG 可用，path/rect/circle/polygon/line/text 直接写
- 不用 SMIL 动画、不用 url(#id) 引用、不加载外部字体/图片
- 箭头用 polygon 画，避开 marker 的 url(#id) 引用

用法：排版脚本 render_body 遇到 [[FIG:key]] 占位符时，输出 figures()[key]。
"""
from __future__ import annotations

import math

PRIMARY = "#3E4C57"
ACCENT = "#8a5a3b"
LIGHT = "#eef1f4"
MID = "#aab4bd"
DARK_TXT = "#3E4C57"
GRAY_TXT = "#6b7680"
WHITE = "#ffffff"
FONT = "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif"


def arrow(x1: float, y1: float, x2: float, y2: float, color: str = PRIMARY,
          width: float = 2.2, head: float = 11) -> str:
    a = math.atan2(y2 - y1, x2 - x1)
    ex, ey = x2 - head * math.cos(a), y2 - head * math.sin(a)
    ax, ay = x2 - head * math.cos(a - 0.42), y2 - head * math.sin(a - 0.42)
    bx, by = x2 - head * math.cos(a + 0.42), y2 - head * math.sin(a + 0.42)
    return (f'<line x1="{x1}" y1="{y1}" x2="{ex:.1f}" y2="{ey:.1f}" '
            f'stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>'
            f'<polygon points="{x2:.1f},{y2:.1f} {ax:.1f},{ay:.1f} {bx:.1f},{by:.1f}" fill="{color}"/>')


def _svg(h: int, inner: str) -> str:
    return (f'<svg viewBox="0 0 640 {h}" width="100%" '
            f'style="height:auto;display:block;margin:26px auto;" '
            f'xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">{inner}</svg>')


def fig_cover() -> str:
    """题图：一个 Agent 在「本地」和「云端」之间搬家，中间一个问号。"""
    s = [
        f'<rect x="0" y="0" width="640" height="300" rx="16" fill="{LIGHT}"/>',
        # 本地电脑
        f'<rect x="58" y="86" width="120" height="80" rx="8" fill="{WHITE}" stroke="{PRIMARY}" stroke-width="2.4"/>',
        f'<path d="M48 176 H188 L198 190 H38 Z" fill="{WHITE}" stroke="{PRIMARY}" stroke-width="2.4" stroke-linejoin="round"/>',
        f'<line x1="78" y1="106" x2="150" y2="106" stroke="{MID}" stroke-width="3" stroke-linecap="round"/>',
        f'<line x1="78" y1="122" x2="136" y2="122" stroke="{MID}" stroke-width="3" stroke-linecap="round"/>',
        f'<text x="118" y="222" text-anchor="middle" font-size="17" fill="{DARK_TXT}">本地</text>',
        # 云
        f'<g fill="{WHITE}" stroke="{PRIMARY}" stroke-width="2.4">',
        f'<circle cx="452" cy="118" r="30"/><circle cx="496" cy="104" r="40"/><circle cx="540" cy="122" r="28"/>',
        f'<rect x="452" y="118" width="88" height="30" rx="15"/>',
        f'</g>',
        f'<text x="496" y="222" text-anchor="middle" font-size="17" fill="{DARK_TXT}">云端</text>',
        # Agent 小机器人
        f'<rect x="288" y="88" width="64" height="58" rx="14" fill="{ACCENT}"/>',
        f'<line x1="320" y1="88" x2="320" y2="72" stroke="{ACCENT}" stroke-width="3" stroke-linecap="round"/>',
        f'<circle cx="320" cy="68" r="5" fill="{ACCENT}"/>',
        f'<circle cx="305" cy="114" r="5" fill="{WHITE}"/><circle cx="335" cy="114" r="5" fill="{WHITE}"/>',
        f'<text x="320" y="170" text-anchor="middle" font-size="13" fill="{GRAY_TXT}">Agent</text>',
        # 双向虚线 + 箭头
        f'<line x1="196" y1="126" x2="284" y2="126" stroke="{PRIMARY}" stroke-width="2.4" stroke-dasharray="6 6"/>',
        arrow(198, 126, 274, 126, PRIMARY),
        f'<line x1="356" y1="126" x2="444" y2="126" stroke="{PRIMARY}" stroke-width="2.4" stroke-dasharray="6 6"/>',
        arrow(358, 126, 434, 126, PRIMARY),
        # 标题
        f'<text x="320" y="266" text-anchor="middle" font-size="20" font-weight="500" fill="{DARK_TXT}">你的 Agent，住在谁家里？</text>',
    ]
    return _svg(300, "".join(s))


def fig_stack() -> str:
    """三层分化：托管同事 / 自托管控制面 / 本地运行时。"""
    rows = [
        (22, PRIMARY, "云", "托管同事", "Claude Cowork · Perplexity Teammates"),
        (120, "#6b7680", "服", "自托管控制面", "Managed Agents · 客户自己的基础设施"),
        (218, ACCENT, "机", "本地运行时", "OpenClaw · ZeroClaw · NanoClaw · Nod"),
    ]
    s = [f'<rect x="0" y="0" width="640" height="312" rx="16" fill="{LIGHT}"/>']
    for y, col, badge, title, sub in rows:
        s += [
            f'<rect x="40" y="{y}" width="560" height="82" rx="12" fill="{WHITE}" stroke="#d4dbe1" stroke-width="1.4"/>',
            f'<rect x="40" y="{y}" width="7" height="82" rx="3.5" fill="{col}"/>',
            f'<circle cx="92" cy="{y+41}" r="24" fill="{col}"/>',
            f'<text x="92" y="{y+48}" text-anchor="middle" font-size="20" fill="{WHITE}">{badge}</text>',
            f'<text x="132" y="{y+37}" font-size="18" font-weight="500" fill="{DARK_TXT}">{title}</text>',
            f'<text x="132" y="{y+61}" font-size="13" fill="{GRAY_TXT}">{sub}</text>',
        ]
    s.append(f'<text x="320" y="300" text-anchor="middle" font-size="12" fill="{GRAY_TXT}">同一个问题，三种 Answers</text>')
    return _svg(312, "".join(s))


def fig_hybrid() -> str:
    """半云半本地：脑子在云端，手伸在本地。"""
    s = [
        f'<rect x="0" y="0" width="640" height="300" rx="16" fill="{LIGHT}"/>',
        f'<line x1="40" y1="150" x2="600" y2="150" stroke="{MID}" stroke-width="1.6" stroke-dasharray="7 7"/>',
        # 云（脑子）
        f'<g fill="{WHITE}" stroke="{PRIMARY}" stroke-width="2.6">',
        f'<circle cx="320" cy="86" r="26"/><circle cx="360" cy="74" r="34"/><circle cx="398" cy="90" r="24"/>',
        f'<rect x="320" y="86" width="78" height="28" rx="14"/>',
        f'</g>',
        f'<text x="359" y="140" text-anchor="middle" font-size="15" fill="{DARK_TXT}">脑子在云端</text>',
        # 伸下的手臂（曲线）
        f'<path d="M359 118 C359 168 300 176 300 214" fill="none" stroke="{ACCENT}" stroke-width="3" stroke-linecap="round"/>',
        f'<circle cx="300" cy="216" r="6" fill="{ACCENT}"/>',
        # 本地电脑（身体）
        f'<rect x="242" y="222" width="116" height="44" rx="6" fill="{WHITE}" stroke="{PRIMARY}" stroke-width="2.4"/>',
        f'<path d="M234 266 H366 L374 278 H226 Z" fill="{WHITE}" stroke="{PRIMARY}" stroke-width="2.4" stroke-linejoin="round"/>',
        f'<text x="300" y="296" text-anchor="middle" font-size="15" fill="{DARK_TXT}">身体伸在本地</text>',
        # 左右标注
        f'<text x="70" y="80" font-size="13" fill="{GRAY_TXT}">合上笔记本</text>',
        f'<text x="70" y="102" font-size="13" fill="{GRAY_TXT}">活还在继续跑</text>',
        f'<text x="470" y="212" font-size="13" fill="{GRAY_TXT}">浏览器 / 本地文件</text>',
        f'<text x="470" y="234" font-size="13" fill="{GRAY_TXT}">仍要 Desktop 开着</text>',
    ]
    return _svg(300, "".join(s))


def fig_loop() -> str:
    """三组 Agent 互相挑刺的循环，中心「没有人审阅」。"""
    nodes = [(320, 62, "写测试"), (150, 236, "跑测试·提单"), (490, 236, "修复")]
    s = [f'<rect x="0" y="0" width="640" height="330" rx="16" fill="{LIGHT}"/>']
    # 循环箭头（顺时针）
    s.append(arrow(360, 96, 196, 214, PRIMARY, 2.4, 13))
    s.append(arrow(486, 238, 200, 238, PRIMARY, 2.4, 13))
    s.append(arrow(180, 214, 288, 104, PRIMARY, 2.4, 13))
    for x, y, label in nodes:
        s += [
            f'<circle cx="{x}" cy="{y}" r="46" fill="{WHITE}" stroke="{PRIMARY}" stroke-width="2.6"/>',
            f'<text x="{x}" y="{y+6}" text-anchor="middle" font-size="15" fill="{DARK_TXT}">{label}</text>',
        ]
    s += [
        f'<text x="320" y="176" text-anchor="middle" font-size="16" font-weight="500" fill="{ACCENT}">没有人审阅</text>',
        f'<text x="320" y="318" text-anchor="middle" font-size="12" fill="{GRAY_TXT}">一个没有人看过的云，被一群机器人围着互相挑刺</text>',
    ]
    return _svg(330, "".join(s))


def figures() -> dict[str, str]:
    return {
        "cover": fig_cover(),
        "stack": fig_stack(),
        "hybrid": fig_hybrid(),
        "loop": fig_loop(),
    }


def build_illustration_files(out_dir) -> dict[str, str]:
    """单独导出 .svg 文件，便于复用或本地查看。"""
    from pathlib import Path
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    figs = figures()
    for key, svg in figs.items():
        (d / f"fig_{key}.svg").write_text(svg, encoding="utf-8")
    return figs
