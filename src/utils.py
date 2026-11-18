"""通用工具：时间、文件、文本、提示词渲染。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def within_hours(s: str, hours: int, reference: datetime | None = None) -> bool:
    """判断 ISO 时间是否在 reference 的过去 hours 小时内；时间解析失败保守保留。"""
    t = parse_iso(s)
    if t is None:
        return True
    ref = reference or datetime.now(timezone(timedelta(hours=8)))
    if t.tzinfo is None:
        t = t.replace(tzinfo=ref.tzinfo)
    return 0 <= (ref - t).total_seconds() <= hours * 3600


def clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", s).strip()


def title_similarity(a: str, b: str) -> float:
    def norm(x: str) -> str:
        return re.sub(r"[\s\W_]+", "", (x or "").lower())
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def load_prompt(root: Path, name: str, **kwargs: Any) -> str:
    """读取 prompts/<name>.md，并用 {{key}} 占位符渲染。

    用双花括号避免与提示词中的 JSON 示例冲突。
    """
    p = root / "prompts" / f"{name}.md"
    text = p.read_text(encoding="utf-8") if p.exists() else f"# {name}\n\n{{{{content}}}}"
    for k, v in kwargs.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def safe_id(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", name).strip("-")[:40]


def extract_json(text: str) -> Any:
    """从 LLM 响应里稳健提取 JSON（支持 ```json 代码块与前后废话）。"""
    if not text:
        raise ValueError("empty LLM response")
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.I)
    payload = m.group(1) if m else text
    payload = payload.strip()
    try:
        return json.loads(payload)
    except Exception:
        pass
    start = min([i for i in (payload.find("["), payload.find("{")) if i >= 0], default=-1)
    if start >= 0:
        for end in range(len(payload), start, -1):
            try:
                return json.loads(payload[start:end])
            except Exception:
                continue
    raise ValueError("no valid JSON found in LLM response")
