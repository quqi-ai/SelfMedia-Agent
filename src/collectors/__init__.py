"""采集管理器：聚合所有启用的采集器 + fixture 兜底。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import NewsItem
from ..utils import read_json, within_hours
from .base import BaseCollector
from .rss import RSSCollector
from .web import WebSearchCollector
from .wechat import WeChatCollector


def run_collectors(settings, since: datetime | None = None, use_fixtures: bool = True) -> tuple[list[NewsItem], list[str]]:
    """返回 (候选资讯, 警告)。since 默认过去 24 小时。"""
    since = since or datetime.now(timezone(timedelta(hours=8)))
    collectors: list[BaseCollector] = [
        RSSCollector(settings.sources, settings),
        WebSearchCollector(settings.sources, settings),
        WeChatCollector(settings.sources, settings),
    ]
    all_items: list[NewsItem] = []
    warns: list[str] = []
    for c in collectors:
        try:
            items, w = c.collect(since)
            all_items.extend(items)
            warns.extend(w)
        except Exception as e:
            warns.append(f"[{c.name}] 采集器异常：{type(e).__name__} {e}")

    # fixture 兜底：dry-run 或联网失败时保证流程可验证（明确标注为样例）
    if use_fixtures and len(all_items) < 5:
        fp = settings.root / settings.sources.get("fixtures", {}).get("news", "fixtures/news_sample.json")
        sample = read_json(fp, []) or []
        hours = settings.config.get("lookback_hours", 24)
        for d in sample:
            d = dict(d)
            # 样例用 hours_ago 相对生成时间，保证永不过 24h 窗口；静态 published_at 仅作展示
            if "hours_ago" in d:
                d["published_at"] = (since - timedelta(hours=float(d.pop("hours_ago")))).isoformat()
            if not within_hours(d.get("published_at", ""), hours, since):
                continue
            it = NewsItem.from_dict(d)
            it.tags = list(dict.fromkeys(it.tags + ["样例"]))
            all_items.append(it)
        warns.append(f"[fixture] 使用本地样例 {len(sample)} 条作为兜底（联网结果不足 5 条）")
    return all_items, warns
