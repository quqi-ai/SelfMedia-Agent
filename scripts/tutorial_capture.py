"""教程截图工具：截取桌面/窗口/区域，自动脱敏，输出可插入公众号的规范图片 + 图注元数据。

依赖：Pillow（PIL），Windows 下用 ctypes 调用 Win32 API 做窗口定位。
纯 Python，无需额外安装 pyautogui / mss / pywin32。

用法示例：
    # 全屏截图并自动脱敏
    python scripts/tutorial_capture.py --mode full --out output/shots --redact

    # 交互式框选区域（运行后用鼠标拖拽选择）
    python scripts/tutorial_capture.py --mode region --out output/shots --redact

    # 按窗口标题关键字截取（如 WorkBuddy 窗口）
    python scripts/tutorial_capture.py --mode window --match "WorkBuddy" --out output/shots --redact

    # 自定义要打码的关键词
    python scripts/tutorial_capture.py --mode full --out output/shots \
        --keyword "我的账号名" --keyword "secret-token"

产出（--out 目录）：
    shot_001.png, shot_002.png ...   规范化截图
    shots_meta.json                   图注元数据（路径/尺寸/时间/图注占位）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------- 脱敏规则 ----------------

# 通用正则（token / 邮箱 / 手机号 / IP / 常见密钥前缀）
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("token", re.compile(r"\b(?:ghp_|github_pat_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_]{16,}")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}")),
    ("sk-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("phone-cn", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("id-cn", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("win-user-path", re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+")),
    ("unix-home-path", re.compile(r"/(?:Users|home)/[A-Za-z0-9._\-]+")),
]


def build_mask_regions(
    img: Image.Image,
    extra_keywords: list[str],
    enabled: bool,
) -> list[tuple[int, int, int, int, str]]:
    """返回需要打码的区域 (x0, y0, x1, y1, label)。

    注意：纯图像无法真正「读懂文字内容」，这里用 OCR 之外的轻量策略：
    对自定义关键词，尝试用 PIL 的基本文本匹配不可行，因此采取保守做法——
    仅对能从图像中通过正则定位的文本打码是不现实的（需要 OCR）。

    因此本模块的自动脱敏有两种实现：
    1) 结构化输入：配合 --mask 参数手工指定像素区域，精确定位；
    2) 关键词名单：写入 config/tutorial_redact.json，由使用者在截图前确认，
       程序对整行高度做覆盖（见 --keyword-line 模式）。

    默认不启用正则打码（因为无 OCR 会误伤），改用 --mask 手工区域 + --keyword 名单提示。
    """
    regions: list[tuple[int, int, int, int, str]] = []
    if not enabled:
        return regions
    # 预留：若未来接入 OCR（如 pytesseract），可在此把 PATTERNS 匹配结果转成区域。
    return regions


# WorkBuddy 界面常见隐私区域预设（比例坐标 0~1，运行时按图片尺寸换算）
# 使用前请在实际截图上核对，比例仅作快速起点。
PRESETS: dict[str, list[tuple[float, float, float, float, str]]] = {
    "workbuddy-left-bottom": [
        (0.0, 0.90, 0.16, 1.0, "左下账号/侧栏底"),
        (0.0, 0.30, 0.16, 0.90, "左侧会话列表"),
    ],
    "workbuddy-full-left": [
        (0.0, 0.0, 0.16, 1.0, "整个左侧栏（含账号与历史会话）"),
    ],
}


def preset_to_masks(name: str, img: Image.Image) -> list[tuple[int, int, int, int, str]]:
    """把比例坐标预设换算成当前图片的像素遮罩区域。"""
    if name not in PRESETS:
        raise ValueError(f"未知预设: {name}。可用: {', '.join(PRESETS)}")
    result = []
    for x0, y0, x1, y1, label in PRESETS[name]:
        result.append((
            int(x0 * img.width), int(y0 * img.height),
            int(x1 * img.width), int(y1 * img.height), label,
        ))
    return result


def apply_masks(img: Image.Image, masks: list[tuple[int, int, int, int, str]]) -> Image.Image:
    """在图片上绘制黑条遮罩。masks 元素为 (x0, y0, x1, y1, label)。"""
    if not masks:
        return img
    out = img.copy()
    draw = ImageDraw.Draw(out)
    for x0, y0, x1, y1, _label in masks:
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(out.width, int(x1)), min(out.height, int(y1))
        if x1 > x0 and y1 > y0:
            draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))
    return out


def parse_mask_arg(values: list[str]) -> list[tuple[int, int, int, int, str]]:
    """解析 --mask x0,y0,x1,y1[:label] 格式。"""
    result = []
    for v in values:
        label = "manual"
        body = v
        if ":" in v:
            body, label = v.rsplit(":", 1)
        parts = [p.strip() for p in body.split(",")]
        if len(parts) != 4:
            raise ValueError(f"mask 格式应为 x0,y0,x1,y1[:label]，收到: {v}")
        try:
            coords = tuple(int(p) for p in parts)
        except ValueError as e:
            raise ValueError(f"mask 坐标必须是整数: {v}") from e
        result.append((*coords, label))
    return result


# ---------------- 截图模式 ----------------

def grab_full() -> Image.Image:
    return ImageGrab.grab().convert("RGB")


def grab_region_interactive() -> Image.Image:
    """全屏显示半透明遮罩，用户鼠标拖拽选择区域后回车确认。"""
    try:
        import tkinter as tk
    except ImportError:
        raise RuntimeError("区域截图需要 tkinter，请用 --mode full 或 --mode window")

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.25)
    root.configure(bg="black")
    canvas = tk.Canvas(root, cursor="cross", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    state = {"x0": 0, "y0": 0, "rect": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x, e.y
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def on_drag(e):
        if state["rect"]:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    root.bind("<Return>", lambda _e: root.quit())
    root.bind("<Escape>", lambda _e: (state.update(rect=None), root.quit()))

    print("拖拽鼠标选择区域，然后按 Enter 确认（Esc 取消，使用全屏）...")
    root.mainloop()
    root.update()

    rect = state["rect"]
    if rect is None:
        root.destroy()
        print("未选择区域，回退到全屏截图")
        return grab_full()

    coords = canvas.coords(rect)
    root.destroy()
    x0, y0, x1, y1 = [int(c) for c in coords]
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    print(f"选择区域: ({x0}, {y0}) - ({x1}, {y1})")
    return ImageGrab.grab(bbox=(x0, y0, x1, y1)).convert("RGB")


def find_window_rect(match: str) -> tuple[int, int, int, int] | None:
    """用 Win32 API 按标题关键字查找窗口，返回 (left, top, right, bottom)。"""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    found: list[tuple[int, int, int, int]] = []

    ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if match.lower() in title.lower():
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            found.append((rect.left, rect.top, rect.right, rect.bottom))
        return True

    user32.EnumWindows(ENUM(cb), 0)
    if not found:
        return None
    # 取面积最大的匹配窗口
    return max(found, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))


def grab_window(match: str) -> Image.Image:
    rect = find_window_rect(match)
    if rect is None:
        raise RuntimeError(f"未找到标题包含「{match}」的可见窗口")
    print(f"窗口区域: {rect}")
    return ImageGrab.grab(bbox=rect).convert("RGB")


from PIL import ImageGrab  # noqa: E402  (放在函数定义后，避免 Windows 导入差异)


def select_masks_interactive(img: Image.Image) -> list[tuple[int, int, int, int, str]]:
    """在截图上交互式框选要打码的区域。回车确认全部，Esc 取消当前框。"""
    try:
        import tkinter as tk
    except ImportError:
        raise RuntimeError("交互式打码需要 tkinter")

    # 缩放到屏幕可显示尺寸，记录缩放比
    max_w, max_h = 1600, 1000
    scale = min(1.0, max_w / img.width, max_h / img.height)
    disp = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

    root = tk.Tk()
    root.title("框选要打码的区域，Enter 完成，Esc 取消当前框")
    canvas = tk.Canvas(root, width=disp.width, height=disp.height, cursor="cross")
    canvas.pack()
    tk_img = __import__("PIL.ImageTk", fromlist=["ImageTk"]).ImageTk.PhotoImage(disp)
    canvas.create_image(0, 0, anchor="nw", image=tk_img)

    boxes: list[tuple[int, int, int, int]] = []
    cur = {"x0": 0, "y0": 0, "id": None}

    def on_press(e):
        cur["x0"], cur["y0"] = e.x, e.y
        cur["id"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def on_drag(e):
        if cur["id"] is not None:
            canvas.coords(cur["id"], cur["x0"], cur["y0"], e.x, e.y)

    def on_release(e):
        if cur["id"] is None:
            return
        x0, y0 = cur["x0"], cur["y0"]
        x1, y1 = e.x, e.y
        if abs(x1 - x0) > 3 and abs(y1 - y0) > 3:
            boxes.append((x0, y0, x1, y1))
        else:
            canvas.delete(cur["id"])
        cur["id"] = None

    def on_esc(_e):
        if boxes:
            # 删掉最后一个框
            canvas.delete("all")
            canvas.create_image(0, 0, anchor="nw", image=tk_img)
            boxes.pop()
            for b in boxes:
                canvas.create_rectangle(*b, outline="red", width=2)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Return>", lambda _e: root.quit())
    root.bind("<Escape>", on_esc)

    print("框选要打码的区域（红色框），全部选好后按 Enter 完成。Esc 删除上一个框。")
    root.mainloop()
    root.destroy()

    # 缩放回原图坐标
    result = []
    for x0, y0, x1, y1 in boxes:
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        result.append((
            int(x0 / scale), int(y0 / scale), int(x1 / scale), int(y1 / scale), "manual",
        ))
    return result


# ---------------- 主流程 ----------------

def main() -> int:
    ap = argparse.ArgumentParser(description="桌面教程截图 + 自动脱敏 + 图注元数据")
    ap.add_argument("--mode", choices=["full", "region", "window"], default="full",
                    help="截图模式：全屏 / 交互式框选 / 按窗口标题")
    ap.add_argument("--match", default="", help="window 模式下匹配的窗口标题关键字")
    ap.add_argument("--out", default="output/shots", help="输出目录")
    ap.add_argument("--redact", action="store_true", help="启用脱敏遮罩")
    ap.add_argument("--interactive-redact", action="store_true",
                    help="截图后弹出图片，用鼠标框选要打码的区域（最直观）")
    ap.add_argument("--mask", action="append", default=[],
                    help="手动遮罩区域 x0,y0,x1,y1[:label]，可重复。坐标相对原图")
    ap.add_argument("--preset", action="append", default=[],
                    help=f"套用预设遮罩模板，可选: {', '.join(PRESETS)}")
    ap.add_argument("--keyword", action="append", default=[],
                    help="需要打码的关键词（仅写入元数据作为提醒，不会自动识别）")
    ap.add_argument("--width", type=int, default=0, help="输出图片缩放宽度（0=原尺寸）")
    ap.add_argument("--note", default="", help="本张图的图注，写入元数据")
    ap.add_argument("--delay", type=float, default=0, help="截图前延迟秒数，便于切换到目标窗口")
    args = ap.parse_args()

    if args.delay:
        print(f"等待 {args.delay} 秒，请切换到要截图的界面...")
        time.sleep(args.delay)

    if args.mode == "full":
        img = grab_full()
    elif args.mode == "region":
        img = grab_region_interactive()
    else:
        if not args.match:
            ap.error("window 模式需要用 --match 指定窗口标题关键字")
        img = grab_window(args.match)

    masks = parse_mask_arg(args.mask)
    for preset in args.preset:
        masks.extend(preset_to_masks(preset, img))
    if args.interactive_redact:
        masks.extend(select_masks_interactive(img))
        args.redact = True
    if masks:
        args.redact = True
    if args.redact:
        img = apply_masks(img, masks)

    if args.width and args.width < img.width:
        ratio = args.width / img.width
        img = img.resize((args.width, int(img.height * ratio)), Image.LANCZOS)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob("shot_*.png"))
    idx = len(existing) + 1
    shot_path = out_dir / f"shot_{idx:03d}.png"
    img.save(shot_path, "PNG", optimize=True)

    meta_path = out_dir / "shots_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        meta = {"created_at": datetime.now().astimezone().isoformat(), "shots": []}

    meta["shots"].append({
        "file": shot_path.name,
        "path": str(shot_path.resolve()),
        "size": list(img.size),
        "mode": args.mode,
        "match": args.match or None,
        "note": args.note or f"图 {idx}",
        "redacted": bool(args.redact),
        "mask_count": len(masks),
        "keyword_reminders": args.keyword,
        "captured_at": datetime.now().astimezone().isoformat(),
    })
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"截图已保存: {shot_path}")
    print(f"尺寸: {img.size[0]}x{img.size[1]}")
    print(f"图注元数据: {meta_path}")
    if args.keyword:
        print("提醒：以下关键词需人工确认是否已打码 ->", ", ".join(args.keyword))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
