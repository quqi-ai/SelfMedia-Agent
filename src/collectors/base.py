"""采集器抽象。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import NewsItem


class BaseCollector(ABC):
    name: str = "base"

    def __init__(self, cfg: dict, settings: object):
        self.cfg = cfg
        self.settings = settings

    @abstractmethod
    def collect(self, since: datetime) -> tuple[list[NewsItem], list[str]]:
        """返回 (资讯列表, 警告列表)。单个源失败不应中断整体采集。"""
        ...
