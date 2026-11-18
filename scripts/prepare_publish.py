"""发布准备：把文章与配图转成公众号草稿箱连接器所需的结构化 payload。

依赖：pip install resvg-py（SVG→PNG，自带二进制无系统依赖）。

产出（output/<date>/publish_prep/）：
- fig_*.png             4 张配图的 PNG（公众号草稿箱只收 jpg/png/webp，不收 SVG）
- image_urls.json       上传后填这里：上传 PNG 换到的公网 URL
- draft_payload.json    文章 blocks 结构（quote/paragraph/image/end），图片 URL 处留占位
- cover.png             题图兼封面

用法：
    python scripts/prepare_publish.py --date 2026-11-17
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def svg_to_png(svg_text: str) -> bytes:
    import resvg_py
    return resvg_py.svg_to_bytes(svg_text)


def md_to_blocks(md_text: str, image_urls: dict[str, str]) -> list[dict]:
    """把卡兹克风格 Markdown 转成连接器 blocks（无小标题，用 lead/paragraph/quote/end）。"""
    lines = md_text.splitlines()
    blocks: list[dict] = []
    title = ""
    fig_map = {"cover": "题图", "hybrid": "半云半本地示意", "stack": "三层分化图", "loop": "三组Agent循环图"}

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            continue
        if line.startswith("【编辑注"):
            break  # 编辑注不进正文
        m = re.fullmatch(r"\[\[FIG:([a-zA-Z0-9_]+)\]\]", line)
        if m:
            key = m.group(1)
            url = image_urls.get(key, f"<UPLOAD_{key.upper()}_URL>")
            blocks.append({"type": "image", "data": {"url": url, "alt": fig_map.get(key, key)}})
            continue
        # 第一段正文做导语（lead）；题图若是首块，其后第一句正文补成 lead
        if not any(b["type"] == "lead" for b in blocks):
            blocks.append({"type": "lead", "content": line})
            continue
        if line.startswith("> "):
            blocks.append({"type": "quote", "content": line[2:].strip()})
        else:
            blocks.append({"type": "paragraph", "content": line})
    if blocks:
        blocks.append({"type": "end", "content": ""})
    return blocks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-11-17")
    a = ap.parse_args()
    out_dir = ROOT / "output" / a.date
    imgs = out_dir / "imgs"
    prep = out_dir / "publish_prep"
    prep.mkdir(parents=True, exist_ok=True)

    # 1) SVG → PNG
    png_sizes: dict[str, int] = {}
    for svg_path in sorted(imgs.glob("fig_*.svg")):
        key = svg_path.stem.replace("fig_", "")
        png = svg_to_png(svg_path.read_text(encoding="utf-8"))
        (prep / f"fig_{key}.png").write_bytes(png)
        png_sizes[key] = len(png)
    # 封面 = 题图
    if (prep / "fig_cover.png").exists():
        (prep / "cover.png").write_bytes((prep / "fig_cover.png").read_bytes())

    # 2) 生成 blocks，图片 URL 留占位（上传后替换）
    md_text = (out_dir / "article_wechat.md").read_text(encoding="utf-8")
    title = next((l[2:].strip() for l in md_text.splitlines() if l.startswith("# ")), "未命名")
    abstract = "当 Claude Cowork 拿掉本地开关、OpenClaw 安全版翻车、亚马逊放出无人审阅的云副本，一个问题是：你的 Agent 到底住在谁家里，出了事谁签字。"
    blocks = md_to_blocks(md_text, {})

    payload = {
        "title": title[:30],
        "abstract": abstract[:100],
        "author": "",
        "source": "WorkBuddy",
        "tags": ["AI", "Agent", "人工智能", "科技", "效率工具"],
        "cover_img": "<UPLOAD_COVER_URL>",
        "blocks": blocks,
    }
    (prep / "draft_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"标题：{payload['title']}（{len(payload['title'])}字）")
    print(f"摘要：{len(payload['abstract'])}字")
    print(f"blocks：{len(blocks)} 块")
    print("PNG 配图：" + ", ".join(f"{k}={v}B" for k, v in png_sizes.items()))
    print(f"封面：{prep / 'cover.png'}")
    print(f"草稿 payload：{prep / 'draft_payload.json'}")
    print("下一步：把 PNG 上传换公网 URL，替换 payload 里的 <UPLOAD_*_URL> 占位符")


if __name__ == "__main__":
    main()
