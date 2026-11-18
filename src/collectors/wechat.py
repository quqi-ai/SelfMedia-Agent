"""公众号素材采集（合规优先，只读素材来源，不抓全文）。

两条通道：
1. endpoints：用户自建的 wechat2rss / 桥接 RSS（需自行保证合规）。
2. fixtures/wechat_manual.json：人工整理的素材清单（标题/链接/发布时间/一句话要点）。

只用于「选题与素材来源」参考，写稿时不复制原文，避免版权风险。
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from ..models import NewsItem
from ..utils import clean_text, read_json, parse_iso
from .base import BaseCollector
from .rss import ATOM, _text


class WeChatCollector(BaseCollector):
    name = "wechat"

    def collect(self, since: datetime) -> tuple[list[NewsItem], list[str]]:
        cfg = self.cfg.get("wechat", {})
        root = getattr(self.settings, "root", None)
        items: list[NewsItem] = []
        warns: list[str] = []

        # 通道 1：桥接 RSS
        if cfg.get("enabled"):
            for ep in cfg.get("endpoints", []):
                try:
                    req = urllib.request.Request(ep, headers={"User-Agent": "SelfMediaAgent/0.1"})
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        root_xml = ET.fromstring(resp.read())
                    nodes = root_xml.findall(".//item") or root_xml.findall(f".//{ATOM}entry")
                    for n in nodes[:20]:
                        title = clean_text(_text(n, "title", f"{ATOM}title"))
                        link = _text(n, "link", f"{ATOM}link")
                        if not link and n.find(f"{ATOM}link") is not None:
                            link = n.find(f"{ATOM}link").get("href", "")
                        pub = _text(n, "pubDate", "published", f"{ATOM}updated")
                        try:
                            dt = parsedate_to_datetime(pub) if pub else None
                        except Exception:
                            dt = parse_iso(pub)
                        if not title or not link:
                            continue
                        items.append(NewsItem(
                            source="微信公众号",
                            title=title,
                            url=link,
                            published_at=dt.isoformat() if dt else datetime.now().astimezone().isoformat(),
                            summary=clean_text(_text(n, "description", f"{ATOM}summary"))[:300],
                            category="热点",
                            tags=["公众号", "素材来源"],
                        ))
                except Exception as e:
                    warns.append(f"[wechat:{ep[:40]}] 失败：{type(e).__name__} {str(e)[:100]}")
        else:
            warns.append("[wechat] 桥接未启用；公众号内容仅通过人工素材清单参考")

        # 通道 2：人工素材清单（永远读取，作为兜底）
        if root:
            manual = read_json(root / "fixtures" / "wechat_manual.json", [])
            for m in manual or []:
                items.append(NewsItem(
                    source=m.get("account", "微信公众号"),
                    title=m.get("title", ""),
                    url=m.get("url", ""),
                    published_at=m.get("published_at", datetime.now().astimezone().isoformat()),
                    summary=m.get("note", "")[:300],
                    category="热点",
                    tags=["公众号", "人工素材"],
                ))
        return items, warns
