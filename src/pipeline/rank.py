"""热度/价值评分与排序：透明可解释的关键词加权 + 时效衰减 + 来源权重。"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

from ..models import NewsItem
from ..utils import parse_iso


def score_item(item: NewsItem, cfg: dict) -> NewsItem:
    r = cfg.get("ranking", {})
    score = float(r.get("base_score", 1.0))
    reasons: list[str] = []
    tags: list[str] = list(item.tags)

    # 1) 来源权重（社区/官方/媒体）
    src_weights = r.get("source_weight", {})
    sw = 1.0
    for k, v in src_weights.items():
        if k.lower() in (item.source or "").lower():
            sw = float(v)
            break
    score *= sw
    if sw > 1.0:
        reasons.append(f"来源权重 {sw}")

    # 2) 关键词命中
    blob = f"{item.title} {item.summary}".lower()
    boost = 0.0
    for kw, w in r.get("keyword_boost", {}).items():
        if kw.lower() in blob:
            boost += float(w)
            tags.append(f"命中:{kw}")
    score += boost
    if boost:
        reasons.append(f"关键词加分 {boost:.1f}")

    # 3) 时效衰减
    pub = parse_iso(item.published_at)
    if pub:
        now = datetime.now(timezone(timedelta(hours=8)))
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=now.tzinfo)
        hours = max(0.0, (now - pub).total_seconds() / 3600)
        half = float(r.get("recency_half_life_hours", 12))
        decay = 2 ** (-hours / half) if half > 0 else 1.0
        score *= (0.5 + 0.5 * decay)
        if hours < 6:
            reasons.append("6小时内新发布")

    # 4) 内容完整度
    if len(item.summary) >= 60:
        score += 0.3
        reasons.append("摘要信息完整")

    # 归一化到 0~10
    item.heat_score = round(min(10.0, score * 1.15), 1)
    item.value_reason = "；".join(dict.fromkeys(reasons)) or "常规收录，暂无显著加分因子"
    item.reason_tags = tags
    item.tags = list(dict.fromkeys(tags))
    return item


def rank_items(items: list[NewsItem], cfg: dict) -> list[NewsItem]:
    scored = [score_item(it, cfg) for it in items]
    return sorted(scored, key=lambda x: (-x.heat_score, x.published_at), reverse=False)
