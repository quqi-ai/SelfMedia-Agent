"""把公众号 Markdown 渲染成符合花叔排版规则的 HTML + 手机预览页。

用法：
    python scripts/build_wechat_preview.py \
        --md  output/2026-11-17/article_wechat.md \
        --out output/2026-11-17 \
        --theme jingyuan

规则依据：prompts/04_wechat_format.md（内联样式 / span 包裹 / 全角标点 /
平台红线 / 三层视觉 / 唯一签名区 / 三连顺序 / 克制用色）。
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

THEMES = {
    "jingyuan": {"name": "静渊", "primary": "#3E4C57", "quote_bg": "#eef1f4", "accent": "#8a5a3b"},
    "moyu": {"name": "摸鱼绿", "primary": "#059669", "quote_bg": "#e9f7f0", "accent": "#059669"},
    "nihui": {"name": "霓灰", "primary": "#4A4458", "quote_bg": "#f0eef3", "accent": "#6d5f8a"},
}
FONT = "-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"

# 标记层关键词（每段最多标 2 处，避免整段划线失去焦点）
MARK_WORDS = ["Agent", "开关", "本地", "云端", "签字", "选择权", "责任", "安全", "通用插头"]


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def mark(text: str, color: str) -> str:
    """给正文关键词加下划线标记，每段最多 2 处。"""
    out, used = text, 0
    for w in MARK_WORDS:
        if used >= 2:
            break
        def repl(m: re.Match) -> str:
            nonlocal used
            if used >= 2 or m.start() < 0:
                return m.group(0)
            used += 1
            return (f'<span style="color:{color};border-bottom:1px solid {color};'
                    f'padding-bottom:1px;">{esc(m.group(0))}</span>')
        out = re.sub(re.escape(w), repl, out, count=1)
    return out


def render_inline(text: str, color: str) -> str:
    """行内渲染：先转义，再做关键词标记（标记内部生成的是合法内联 span）。"""
    protected: list[str] = []
    def stash(m: re.Match) -> str:
        protected.append(m.group(0))
        return f"\x00{len(protected)-1}\x00"
    text = re.sub(r"「[^」]+」", stash, text)  # 引用词不加下划线
    text = esc(text)
    text = mark(text, color)
    for i, s in enumerate(protected):
        text = text.replace(f"\x00{i}\x00",
                            f'<span style="color:{color};">{esc(s)}</span>')
    return text


def render_body(lines: list[str], t: dict, figs: dict[str, str] | None = None) -> str:
    out: list[str] = []
    primary, quote_bg = t["primary"], t["quote_bg"]
    note_lines: list[str] = []
    in_note = False
    figs = figs or {}

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        # 配图占位符 [[FIG:key]] → 内联 SVG（纯代码绘制，无外部依赖）
        m = re.fullmatch(r"\[\[FIG:([a-zA-Z0-9_]+)\]\]", line)
        if m and m.group(1) in figs:
            out.append(figs[m.group(1)])
            continue
        if line.startswith("【编辑注"):
            in_note = True
        if in_note:
            note_lines.append(line)
            continue
        if line.startswith("# "):
            continue  # 标题单独渲染到头部
        if line.startswith("> "):
            q = render_inline(line[2:].strip(), primary)
            out.append(
                f'<blockquote style="margin:26px 0;padding:18px 20px;'
                f'background:{quote_bg};border-left:4px solid {primary};border-radius:0 8px 8px 0;">'
                f'<span style="font-size:17px;line-height:1.85;color:{primary};font-weight:500;">{q}</span>'
                f'</blockquote>'
            )
        else:
            body = render_inline(line, primary)
            out.append(
                f'<p style="margin:0 0 20px 0;font-size:16px;line-height:1.95;color:#333;">'
                f'<span style="font-size:16px;line-height:1.95;color:#333;">{body}</span></p>'
            )

    # 唯一签名区 / 三连卡片（顺序 点赞 → 转发 → 推荐）
    sign = (
        f'<section style="margin:36px 0 8px 0;padding:22px 18px;background:{quote_bg};border-radius:12px;text-align:center;">'
        f'<span style="display:block;font-size:13px;line-height:1.8;color:#888;margin-bottom:10px;">'
        f'如果这篇文章让你有一点点触动</span>'
        f'<span style="display:inline-block;font-size:15px;line-height:1;color:#fff;background:{primary};'
        f'padding:10px 22px;border-radius:22px;margin:0 4px;">点赞</span>'
        f'<span style="display:inline-block;font-size:15px;line-height:1;color:#fff;background:{primary};'
        f'padding:10px 22px;border-radius:22px;margin:0 4px;">转发</span>'
        f'<span style="display:inline-block;font-size:15px;line-height:1;color:#fff;background:{primary};'
        f'padding:10px 22px;border-radius:22px;margin:0 4px;">推荐</span>'
        f'<span style="display:block;font-size:12px;line-height:1.8;color:#999;margin-top:14px;">'
        f'星标不迷路，我们下次再见</span>'
        f'</section>'
    )
    out.append(sign)

    if note_lines:
        note = " ".join(note_lines)
        out.append(
            f'<p style="margin:24px 0 0 0;font-size:12px;line-height:1.7;color:#aaa;">'
            f'<span style="font-size:12px;line-height:1.7;color:#aaa;">{esc(note)}</span></p>'
        )
    return "\n".join(out)


def build_paste(md_text: str, t: dict, figs: dict[str, str] | None = None) -> tuple[str, str]:
    lines = md_text.splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "未命名文章")
    primary = t["primary"]
    header = (
        f'<section style="padding:0 2px;font-family:{FONT};">'
        f'<h1 style="font-size:22px;line-height:1.5;color:#222;font-weight:500;margin:8px 0 24px 0;">'
        f'<span style="font-size:22px;line-height:1.5;color:#222;font-weight:500;">{esc(title)}</span></h1>'
    )
    body = render_body(lines, t, figs)
    paste = header + body + "</section>"
    # 平台红线校验
    banned = [(r"class\s*=", "class 属性"), (r"\bid\s*=", "id 属性"),
              (r"position\s*:", "position 定位"), (r"display\s*:\s*grid", "grid 布局"),
              (r"@media|@keyframes", "@media/@keyframes"), (r"var\s*\(\s*--", "CSS 变量"),
              (r"href\s*=", "可点击外链"), (r"<script", "script 标签"), (r"float\s*:", "float")]
    warnings = [msg for pat, msg in banned if re.search(pat, paste, re.I)]
    return paste, "|".join(warnings)


def build_preview(paste: str, title: str, t: dict) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>公众号排版预览 · {esc(title)}</title>
<style>
  *{{box-sizing:border-box;}}
  body{{margin:0;background:#1c1e22;font-family:{FONT};color:#e8e8e8;}}
  .wrap{{max-width:520px;margin:0 auto;padding:28px 16px 60px;}}
  .bar{{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;}}
  .bar h2{{font-size:14px;font-weight:500;margin:0;color:#bbb;}}
  .theme{{font-size:12px;color:#888;border:1px solid #444;border-radius:14px;padding:4px 12px;}}
  .phone{{background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.4);}}
  .topbar{{height:52px;display:flex;align-items:center;justify-content:center;border-bottom:1px solid #f0f0f0;font-size:15px;color:#333;position:relative;}}
  .topbar .bk{{position:absolute;left:18px;color:#576b95;font-size:14px;}}
  .article{{padding:18px 18px 30px;}}
  .copy{{display:block;width:100%;margin-top:16px;background:{t['primary']};color:#fff;border:0;border-radius:10px;padding:13px;font-size:14px;cursor:pointer;}}
  .tip{{font-size:12px;color:#777;line-height:1.7;margin-top:12px;text-align:center;}}
</style></head><body>
<div class="wrap">
  <div class="bar"><h2>公众号排版预览 · 手机视图</h2><span class="theme">主题 {t['name']}</span></div>
  <div class="phone">
    <div class="topbar"><span class="bk">‹ 返回</span>数字生命卡兹克</div>
    <div class="article" id="art">{paste}</div>
  </div>
  <button class="copy" onclick="cp()">复制排版正文（到公众号 Ctrl+V）</button>
  <div class="tip">点按钮复制的是渲染后的富文本（不是 HTML 源码）。<br>到公众号后台正文区 Ctrl+V 粘贴，样式随文字一起带上。<br>封面需在公众号后台手动设置。</div>
</div>
<script>
// 复制渲染后的富文本（而非 innerHTML 源码）。用 Range 选中 DOM 后 execCommand('copy')，
// 剪贴板里同时带 text/html 和 text/plain，粘贴到公众号编辑器才有样式。
function cp(){{
  var el=document.getElementById('art');
  var sel=window.getSelection();
  var range=document.createRange();
  range.selectNodeContents(el);
  sel.removeAllRanges();
  sel.addRange(range);
  var ok=false;
  try{{ok=document.execCommand('copy');}}catch(e){{}}
  sel.removeAllRanges();
  if(ok){{alert('已复制排版正文，去公众号正文区 Ctrl+V 粘贴');}}
  else{{alert('自动复制失败，请手动框选上方文章正文后 Ctrl+C');}}
}}
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--theme", default="jingyuan", choices=list(THEMES))
    a = ap.parse_args()
    md_path, out_dir = Path(a.md), Path(a.out)
    t = THEMES[a.theme]
    md_text = md_path.read_text(encoding="utf-8")
    # 代码绘制配图（内联 SVG），同时导出独立 .svg 便于复用
    try:
        import illustrations
        figs = illustrations.build_illustration_files(out_dir / "imgs")
        fig_count = len(figs)
    except Exception as e:
        figs, fig_count = {}, 0
        print(f"[警告] 配图生成跳过：{e}")
    paste, warnings = build_paste(md_text, t, figs)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "article_wechat_paste.html").write_text(paste, encoding="utf-8")
    title = next((l[2:].strip() for l in md_text.splitlines() if l.startswith("# ")), "文章")
    preview = build_preview(paste, title, t)
    (out_dir / "preview.html").write_text(preview, encoding="utf-8")
    # 校验 SVG 合规：不得含 SMIL 动画或 url(#id) 引用
    svg_bad = []
    for key, svg in figs.items():
        if re.search(r"<animate|SMIL", svg) or re.search(r"url\s*\(\s*#", svg):
            svg_bad.append(key)
    print(f"主题：{t['name']}")
    print(f"配图：{fig_count} 张内联 SVG（{'合规' if not svg_bad else '违规 ' + str(svg_bad)}）")
    print(f"粘贴版 HTML：{out_dir / 'article_wechat_paste.html'}")
    print(f"手机预览页：{out_dir / 'preview.html'}")
    print(f"平台红线校验：{'通过（0 命中）' if not warnings else '警告 ' + warnings}")


if __name__ == "__main__":
    main()
