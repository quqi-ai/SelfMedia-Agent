"""核心数据结构：用 dataclass 定义，天然可 JSON 序列化。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .utils import now_iso, title_similarity


@dataclass
class NewsItem:
    """一条采集到的资讯（整理/去重/评分后）。"""

    source: str                       # 来源名，如 机器之心 / Hacker News
    title: str
    url: str
    published_at: str                 # ISO-8601 发布时间
    summary: str = ""                 # 摘要
    category: str = "AI"              # AI / 科技 / Agent / 热点
    tags: list[str] = field(default_factory=list)
    heat_score: float = 0.0           # 0~10 的热度/价值分
    value_reason: str = ""            # 为什么值得收进来的理由
    reason_tags: list[str] = field(default_factory=list)  # 命中的加分因子
    collected_at: str = field(default_factory=now_iso)
    id: str = ""                      # 基于 URL 的稳定 id

    def __post_init__(self) -> None:
        if not self.id:
            self.id = hashlib.md5(canonical_url(self.url).encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NewsItem":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Topic:
    """公众号文章选题，等待人工确认。"""

    id: str
    title: str                        # 标题（候选）
    angle: str                        # 切入角度
    core_thesis: str                  # 核心论点
    material_sources: list[str] = field(default_factory=list)  # 素材来源（NewsItem.id / URL / 公众号）
    priority: str = "B"               # S / A / B
    value_reason: str = ""            # 为什么现在值得写
    status: str = "pending"           # pending / confirmed / rejected
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Topic":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ArticleDraft:
    """文章初稿（公众号优先，其次小红书）。"""

    id: str
    topic_id: str
    platform: str                     # wechat / xiaohongshu
    title: str
    body_markdown: str = ""
    body_html: str = ""               # 花叔排版规则渲染后的 HTML（可选）
    source_refs: list[str] = field(default_factory=list)
    style_notes: str = ""             # 风格与自检报告摘要
    status: str = "draft"             # draft / confirmed / rejected
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunState:
    """某一天的流程状态（人工确认门控的载体）。"""

    date: str
    stage: str = "collected"          # collected / scripted / topics_pending / topics_confirmed / drafts_pending / drafts_confirmed / publish_pending / published
    confirmed_topic_ids: list[str] = field(default_factory=list)
    confirmed_draft_ids: list[str] = field(default_factory=list)
    transcript_path: str = ""
    warnings: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RunState":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "from", "ref", "share_token", "src", "fbclid", "gclid",
}


def canonical_url(url: str, drop_tracking: Optional[set[str]] = None) -> str:
    """URL 归一化：去协议/www/末尾斜杠、去追踪参数、参数排序，用于去重。"""
    drop = drop_tracking if drop_tracking is not None else _TRACKING_PARAMS
    try:
        p = urlsplit((url or "").strip())
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = (p.path or "/").rstrip("/") or "/"
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in drop]
        return urlunsplit((p.scheme.lower(), netloc, path, urlencode(sorted(query)), ""))
    except Exception:
        return (url or "").strip()


def deduplicate(items: list[NewsItem], threshold: float = 0.86,
                drop_tracking: Optional[set[str]] = None) -> list[NewsItem]:
    """去重：先 URL 归一化精确去重，再标题相似度去重；保留信息更全的一条。"""
    by_url: dict[str, NewsItem] = {}
    for it in items:
        key = canonical_url(it.url, drop_tracking)
        it.id = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
        prev = by_url.get(key)
        if prev is None or _richer(it, prev):
            by_url[key] = it

    kept: list[NewsItem] = []
    for it in by_url.values():
        dup_of = None
        for k in kept:
            if title_similarity(it.title, k.title) >= threshold:
                dup_of = k
                break
        if dup_of is None:
            kept.append(it)
        else:
            if _richer(it, dup_of):
                idx = kept.index(dup_of)
                it.value_reason = (it.value_reason + "；多源重复报道，已合并").strip("；")
                kept[idx] = it
            else:
                dup_of.value_reason = (dup_of.value_reason + "；多源重复报道，已合并").strip("；")
    return kept


def _richer(a: NewsItem, b: NewsItem) -> bool:
    """信息完整度比较：摘要更长、时间更新者胜出。"""
    return (len(a.summary), a.published_at) > (len(b.summary), b.published_at)


def to_markdown_table(items: list[NewsItem]) -> str:
    """把资讯整理成 Markdown 表格（来源/标题/链接/发布时间/摘要/热度/价值理由）。"""
    lines = [
        "| 来源 | 标题 | 链接 | 发布时间 | 摘要 | 热度 | 价值理由 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for it in items:
        title = it.title.replace("|", "/").replace("\n", " ")
        summary = it.summary.replace("|", "/").replace("\n", " ")[:90]
        reason = it.value_reason.replace("|", "/").replace("\n", " ")[:70]
        lines.append(
            f"| {it.source} | {title} | [链接]({it.url}) | {it.published_at[:19]} "
            f"| {summary} | {it.heat_score:.1f} | {reason} |"
        )
    return "\n".join(lines)
