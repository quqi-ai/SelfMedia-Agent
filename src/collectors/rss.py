"""RSS/Atom 采集：标准库 urllib + xml.etree，无第三方依赖。

支持 RSS2.0（channel/item）与 Atom（feed/entry），兼容 dc:date、content:encoded。
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from ..models import NewsItem
from ..utils import clean_text, parse_iso, within_hours
from .base import BaseCollector

UA = "Mozilla/5.0 (compatible; SelfMediaAgent/0.1; +local-rss-reader)"
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"


def _text(node: ET.Element, *paths: str) -> str:
    for p in paths:
        el = node.find(p)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def _published(node: ET.Element) -> str:
    for path in ("pubDate", "published", "updated", f"{DC}date"):
        val = _text(node, path)
        if not val:
            continue
        try:
            dt = parsedate_to_datetime(val)
            if dt:
                return dt.isoformat()
        except Exception:
            pass
        dt = parse_iso(val)
        if dt:
            return dt.isoformat()
    return ""


class RSSCollector(BaseCollector):
    name = "rss"

    def collect(self, since: datetime) -> tuple[list[NewsItem], list[str]]:
        items: list[NewsItem] = []
        warns: list[str] = []
        feeds = [f for f in self.cfg.get("rss", []) if f.get("enabled")]
        for feed in feeds:
            url = feed.get("url", "")
            if not url:
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                root = ET.fromstring(raw)
                nodes = root.findall(".//item") or root.findall(f".//{ATOM}entry")
                for n in nodes[:40]:
                    title = clean_text(_text(n, "title", f"{ATOM}title"))
                    link = _text(n, "link", f"{ATOM}link")
                    if not link and n.find(f"{ATOM}link") is not None:
                        link = n.find(f"{ATOM}link").get("href", "")
                    if not title or not link:
                        continue
                    pub = _published(n)
                    summary = clean_text(_text(n, "description", "summary", f"{ATOM}summary", f"{CONTENT}encoded"))[:500]
                    if not within_hours(pub, 24, since):
                        continue
                    items.append(NewsItem(
                        source=feed.get("name", url),
                        title=title,
                        url=link,
                        published_at=pub or datetime.now(timezone(timedelta(hours=8))).isoformat(),
                        summary=summary,
                        category=feed.get("category", "科技"),
                        tags=[feed.get("category", "科技")],
                    ))
            except Exception as e:
                warns.append(f"[rss:{feed.get('name', url)}] 采集失败：{type(e).__name__} {str(e)[:120]}")
        return items, warns
