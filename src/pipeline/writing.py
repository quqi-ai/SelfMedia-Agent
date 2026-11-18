"""文章初稿生成：公众号优先（卡兹克风格 + 花叔排版），再生成小红书版本。"""
from __future__ import annotations

import re
from pathlib import Path

from ..config import Settings
from ..llm.base import BaseLLM
from ..models import ArticleDraft, NewsItem, Topic
from ..utils import extract_json, load_prompt, safe_id, write_text


def _style_report(md: str) -> str:
    """卡兹克四层自检的机械化部分（L1 硬性规则），输出简报。"""
    banned_words = ["说白了", "意味着什么", "这意味着", "本质上", "换句话说", "不可否认",
                    "综上所述", "值得注意的是", "不难发现", "让我们来看看", "在当今", "首先"]
    hits = [w for w in banned_words if w in md]
    banned_punct = {"：": "冒号", "——": "破折号", '"': "双引号", "“": "左双引号", "”": "右双引号"}
    punct_hits = [name for ch, name in banned_punct.items() if ch in md]
    return (
        "L1 硬性规则扫描：" +
        (f"禁用词命中 {hits}" if hits else "禁用词 0 命中") + "；" +
        (f"禁用标点命中 {punct_hits}" if punct_hits else "禁用标点 0 命中") +
        "。注：L2-L4 需人工通读终审。"
    )


def generate_wechat_draft(settings: Settings, llm: BaseLLM, topic: Topic,
                          items: list[NewsItem], workdir: Path) -> ArticleDraft:
    system = load_prompt(settings.root, "00_system")
    materials = "\n".join(f"- {it.title}｜{it.source}｜{it.summary[:150]}" for it in items[:8])
    style_rules = load_prompt(settings.root, "03_kazix_style")
    format_rules = load_prompt(settings.root, "04_wechat_format")
    prompt = load_prompt(
        settings.root, "05_wechat_draft",
        title=topic.title, angle=topic.angle, thesis=topic.core_thesis,
        materials=materials or "（无联网素材，使用内置样例）",
        style_rules=style_rules, format_rules=format_rules,
    )
    resp = llm.complete(system, prompt)
    body = resp.text.strip()
    if body.startswith("# "):
        title = body.splitlines()[0][2:].strip()
    else:
        title = topic.title
    draft = ArticleDraft(
        id=f"d-{safe_id(topic.title)[:16]}",
        topic_id=topic.id,
        platform="wechat",
        title=title,
        body_markdown=body,
        source_refs=topic.material_sources,
        style_notes=_style_report(body),
    )
    write_text(workdir / f"{draft.id}_wechat.md", body)
    return draft


def generate_xiaohongshu(settings: Settings, llm: BaseLLM, topic: Topic,
                         wechat_md: str, workdir: Path) -> ArticleDraft:
    system = load_prompt(settings.root, "00_system")
    prompt = load_prompt(
        settings.root, "06_xiaohongshu",
        title=topic.title, thesis=topic.core_thesis,
        wechat_excerpt=wechat_md[:1500],
    )
    resp = llm.complete(system, prompt)
    body = resp.text.strip()
    draft = ArticleDraft(
        id=f"x-{safe_id(topic.title)[:16]}",
        topic_id=topic.id,
        platform="xiaohongshu",
        title=topic.title,
        body_markdown=body,
        source_refs=topic.material_sources,
        style_notes="小红书版：标题备选 + 短段落 + 话题标签；需人工配图与改写",
    )
    write_text(workdir / f"{draft.id}_xhs.md", body)
    return draft


def render_wechat_html(md: str, theme_color: str = "#059669") -> tuple[str, list[str]]:
    """极简 Markdown → 公众号 HTML，遵循花叔排版硬规则（内联样式 / span 包裹 / 无外链）。

    返回 (html, warnings)。真实生产建议改用 gzh-design-skill 完整组件库 + 校验脚本。
    """
    lines = md.splitlines()
    out: list[str] = []
    warnings: list[str] = []
    para: list[str] = []

    def span(text: str, style: str = "") -> str:
        esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        st = style or "font-size:16px;line-height:1.9;color:#333;"
        return f'<span style="{st}">{esc}</span>'

    def inline(text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", lambda m: span(m.group(1), f"font-size:16px;line-height:1.9;color:{theme_color};font-weight:bold;"), text)
        text = re.sub(r"「(.+?)」", lambda m: m.group(0), text)
        # 去除 Markdown 链接的可点击性（公众号外链会被过滤），保留文字
        text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
        return text

    def flush() -> None:
        if para:
            out.append(f'<p style="margin:0 0 18px 0;">{inline(" ".join(para))}</p>')
            para.clear()

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("# "):
            flush()
            out.append(f'<h1 style="font-size:22px;line-height:1.5;color:{theme_color};font-weight:bold;margin:24px 0 18px 0;">{span(line[2:].strip(), f"font-size:22px;line-height:1.5;color:{theme_color};font-weight:bold;")}</h1>')
        elif line.startswith("## "):
            flush()
            txt = re.sub(r"^\d+[\.、]\s*", "", line[3:].strip())
            out.append(f'<h2 style="font-size:18px;line-height:1.6;color:{theme_color};font-weight:bold;margin:22px 0 14px 0;">{span(txt, f"font-size:18px;line-height:1.6;color:{theme_color};font-weight:bold;")}</h2>')
        elif line.startswith("> "):
            flush()
            out.append(f'<blockquote style="border-left:3px solid {theme_color};background:#f7f8fa;padding:12px 14px;margin:16px 0;font-size:15px;color:#666;">{span(line[2:].strip(), "font-size:15px;line-height:1.8;color:#666;")}</blockquote>')
        elif not line.strip():
            flush()
        else:
            para.append(line.strip())
    flush()

    html = '<section style="padding:0 4px;font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;">' + "".join(out) + "</section>"

    # 硬规则校验（对应花叔排版 skill 的校验脚本思路）
    forbidden = [
        (r"class\s*=", "出现 class 属性（公众号会过滤）"),
        (r"\bid\s*=", "出现 id 属性（公众号会过滤）"),
        (r"position\s*:", "出现 position 定位（公众号会过滤）"),
        (r"display\s*:\s*grid", "出现 grid 布局（公众号会过滤）"),
        (r"@media|@keyframes", "出现 @media/@keyframes（公众号会过滤）"),
        (r"var\s*\(\s*--", "出现 CSS 变量（公众号会过滤）"),
        (r"href\s*=", "出现可点击外链（公众号会过滤成裸 URL）"),
        (r"<script", "出现 script 标签"),
        (r"float\s*:", "出现 float（公众号会过滤）"),
    ]
    for pat, msg in forbidden:
        if re.search(pat, html, flags=re.I):
            warnings.append(msg)
    return html, warnings
