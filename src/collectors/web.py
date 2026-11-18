"""Web 搜索采集（接口预留）。

未配置 endpoint 时返回空结果 + warning，不伪造数据；
配置了兼容 Serper/Tavily 风格的 JSON 接口后即可联网采集。
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime

from ..models import NewsItem
from ..utils import clean_text, now_iso, parse_iso
from .base import BaseCollector


class WebSearchCollector(BaseCollector):
    name = "web_search"

    def collect(self, since: datetime) -> tuple[list[NewsItem], list[str]]:
        cfg = self.cfg.get("web_search", {})
        if not cfg.get("enabled") or not cfg.get("endpoint"):
            return [], ["[web_search] 未配置 endpoint，已跳过（可在 config/sources.json 启用）"]

        api_key = os.environ.get(cfg.get("api_key_env", "SEARCH_API_KEY"), "")
        items: list[NewsItem] = []
        warns: list[str] = []
        for q in cfg.get("queries", []):
            try:
                params = urllib.parse.urlencode({"q": q, "num": cfg.get("max_results_per_query", 10)})
                url = cfg["endpoint"].rstrip("/") + ("&" if "?" in cfg["endpoint"] else "?") + params
                headers = {"User-Agent": "SelfMediaAgent/0.1"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for r in data.get("organic", data.get("results", data.get("data", [])))[:20]:
                    link = r.get("link") or r.get("url", "")
                    title = clean_text(r.get("title", ""))
                    if not link or not title:
                        continue
                    pub = r.get("date") or r.get("published_at") or r.get("publishedDate", "")
                    dt = parse_iso(pub)
                    items.append(NewsItem(
                        source=r.get("source", "Web"),
                        title=title,
                        url=link,
                        published_at=dt.isoformat() if dt else now_iso(),
                        summary=clean_text(r.get("snippet") or r.get("description", ""))[:500],
                        category="热点",
                        tags=["web_search"],
                    ))
            except Exception as e:
                warns.append(f"[web_search:{q[:16]}] 失败：{type(e).__name__} {str(e)[:100]}")
        return items, warns
