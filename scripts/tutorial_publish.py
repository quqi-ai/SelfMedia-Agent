"""教程文章配图发布辅助：读取截图元数据，生成上传清单与公众号图位 payload。

设计：图片上传需通过红草 MCP 工具完成（本脚本不内置任何密钥）。
流程：
  1) 本脚本读取 shots_meta.json，生成 upload_list.json（待上传图片清单）
  2) 使用者/agent 用红草 get_upload_channel(image_base64=...) 上传每张图，拿到公网 URL
  3) 把 URL 回填到 upload_list.json 的 url 字段
  4) 本脚本 --build 生成公众号 payload（image blocks + 图注），可直接交给发布流程

用法：
    # 步骤1：生成上传清单
    python scripts/tutorial_publish.py --shots output/shots --prepare

    # 步骤3：上传并回填 url 后，生成文章图位 payload
    python scripts/tutorial_publish.py --shots output/shots --build \
        --title "WorkBuddy 教程" --out output/tutorial_article.json
"""
from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime
from pathlib import Path


def load_meta(shots_dir: Path) -> dict:
    p = shots_dir / "shots_meta.json"
    if not p.exists():
        raise SystemExit(f"未找到图注元数据: {p}，请先运行 tutorial_capture.py")
    return json.loads(p.read_text(encoding="utf-8"))


def prepare(shots_dir: Path) -> None:
    meta = load_meta(shots_dir)
    items = []
    for s in meta["shots"]:
        path = shots_dir / s["file"]
        if not path.exists():
            print(f"警告: 缺少图片 {path}")
            continue
        raw = path.read_bytes()
        items.append({
            **s,
            "base64": base64.b64encode(raw).decode("ascii"),
            "mime": "image/png",
            "url": "",  # 待回填：红草上传后返回的公网 URL
        })
    out = shots_dir / "upload_list.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"上传清单已生成: {out}")
    print(f"共 {len(items)} 张图待上传到图床（用红草 get_upload_channel 上传 image_base64）")
    for it in items:
        print(f"  - {it['file']}  {it['note']}")


def build(shots_dir: Path, title: str, out_path: Path) -> None:
    p = shots_dir / "upload_list.json"
    if not p.exists():
        raise SystemExit(f"未找到上传清单: {p}，请先 --prepare 并回填 url")
    items = json.loads(p.read_text(encoding="utf-8"))
    missing = [i["file"] for i in items if not i.get("url")]
    if missing:
        raise SystemExit(f"以下图片尚未上传（url 为空）: {', '.join(missing)}")

    blocks: list[dict] = []
    for i, it in enumerate(items, 1):
        note = it.get("note") or f"图 {i}"
        blocks.append({"type": "image", "url": it["url"], "alt": note})
        blocks.append({"type": "paragraph", "content": f"{note}"})

    payload = {
        "title": title,
        "blocks": blocks,
        "image_count": len(items),
        "generated_at": datetime.now().astimezone().isoformat(),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"文章图位 payload 已生成: {out_path}")
    print(f"  {len(items)} 张图 + {len(items)} 条图注")
    print("  可直接把 blocks 交给红草 create_article 写入草稿箱")


def main() -> int:
    ap = argparse.ArgumentParser(description="教程配图上传清单与公众号图位 payload 生成")
    ap.add_argument("--shots", required=True, help="截图目录（含 shots_meta.json）")
    ap.add_argument("--prepare", action="store_true", help="生成上传清单")
    ap.add_argument("--build", action="store_true", help="生成文章图位 payload")
    ap.add_argument("--title", default="", help="文章标题（--build 时用）")
    ap.add_argument("--out", default="", help="payload 输出路径（--build 时用）")
    args = ap.parse_args()

    shots = Path(args.shots)
    if not shots.exists():
        raise SystemExit(f"截图目录不存在: {shots}")

    if args.prepare:
        prepare(shots)
    elif args.build:
        if not args.title or not args.out:
            ap.error("--build 需要 --title 和 --out")
        build(shots, args.title, Path(args.out))
    else:
        ap.error("请选择 --prepare 或 --build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
